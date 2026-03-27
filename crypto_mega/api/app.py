"""FastAPI application — REST API + WebSocket for the entire system."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

# Configure logging early so startup issues are visible in Railway logs
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


class RingBufferLogHandler(logging.Handler):
    """Captures log records into a ring buffer for the UI log viewer."""

    def __init__(self, capacity: int = 2000):
        super().__init__()
        self.capacity = capacity
        self.records: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        entry = {
            "ts": record.created,
            "level": record.levelname,
            "logger": record.name,
            "msg": self.format(record),
        }
        self.records.append(entry)
        if len(self.records) > self.capacity:
            self.records = self.records[-self.capacity:]

    def get_recent(self, limit: int = 200, since: float = 0.0) -> list[dict]:
        if since > 0:
            return [r for r in self.records if r["ts"] > since][-limit:]
        return self.records[-limit:]


# Attach ring buffer to all crypto_mega loggers
_log_buffer = RingBufferLogHandler(capacity=2000)
_log_buffer.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
_log_buffer.setLevel(logging.DEBUG)
logging.getLogger("crypto_mega").addHandler(_log_buffer)

from crypto_mega.backtester.backtester import Backtester
from crypto_mega.config.settings import RiskConfig, SystemConfig
from crypto_mega.data.provider import DataProvider
from crypto_mega.engine.signal_engine import SignalEngine
from crypto_mega.execution.executor import ExecutionEngine, ExchangeConnection
from crypto_mega.monitor.monitor import PerformanceMonitor
from crypto_mega.paper.tracker import PaperTracker
from crypto_mega.resource_manager.manager import ResourceManager
from crypto_mega.risk.risk_manager import RiskManager
from crypto_mega.strategies.loader import strategy_loader
from crypto_mega.utils.types import Signal, StrategyConfig, TimeFrame

logger = logging.getLogger(__name__)


# ─── WebSocket connection manager ───

class ConnectionManager:
    """Manages WebSocket connections for real-time signal streaming."""

    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected, total: {len(self.active)}")

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected, total: {len(self.active)}")

    async def broadcast(self, message: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)


ws_manager = ConnectionManager()


# ─── App lifecycle ───

config = SystemConfig()
data_provider = DataProvider()
signal_engine = SignalEngine(data_provider)
execution_engine = ExecutionEngine()
resource_manager = ResourceManager(total_workers=config.resources.max_workers, mode="hybrid")
monitor = PerformanceMonitor()
risk_manager = RiskManager(config.risk)
paper_tracker = PaperTracker()
backtester = Backtester()
db_session = None
_engine_task = None  # background task for signal engine loop
_candle_collector = None  # background CandleCollector instance
_strategy_explorer = None  # background StrategyExplorer instance
_explorer_task = None  # background task for explorer loop
_shutdown_event = asyncio.Event()  # Signal graceful shutdown
_last_health_check = time.time()
_health_check_interval = 60  # Log health every 60 seconds
_app_start_time = time.time()

# System-wide alert/problem tracking
_system_alerts: list[dict] = []  # [{ts, level, component, message}]


def add_system_alert(level: str, component: str, message: str):
    """Add a system alert visible in the UI status banner. Deduplicates recent alerts."""
    now = time.time()
    # Deduplicate: don't repeat the same component+level within 5 minutes
    for existing in reversed(_system_alerts):
        if now - existing["ts"] > 300:
            break  # only check last 5 min
        if existing["component"] == component and existing["level"] == level:
            return  # already have a recent alert for this

    _system_alerts.append({
        "ts": now,
        "level": level,
        "component": component,
        "message": message,
    })
    # Keep last 100
    if len(_system_alerts) > 100:
        _system_alerts[:] = _system_alerts[-100:]
    if level == "error":
        logger.error(f"[ALERT:{component}] {message}")
    else:
        logger.warning(f"[ALERT:{component}] {message}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle. Graceful — never crashes on missing deps."""
    global db_session

    global _app_start_time
    _app_start_time = time.time()

    # Init database with background retry — app starts fast, DB connects when ready
    db_retry_task = asyncio.create_task(_connect_db_with_retry())

    # Load strategies from directory
    try:
        strategy_loader.load_directory(config.strategies_dir)
        loaded = list(strategy_loader.list_all().keys())
        logger.info(f"Loaded strategies from {config.strategies_dir}: {loaded}")
        if not loaded:
            add_system_alert(
                "warning", "strategies",
                f"No strategies found in {config.strategies_dir}/"
            )
    except Exception as e:
        logger.warning(f"Could not load strategies: {e}")
        add_system_alert("error", "strategies", f"Failed to load strategies: {e}")

    # Start periodic health monitor
    health_task = asyncio.create_task(periodic_health_check())

    # Auto-start engine if AUTO_START env is set (default: true for Railway)
    auto_start = os.getenv("AUTO_START_ENGINE", "true").lower() == "true"
    if auto_start and strategy_loader.list_all():
        auto_task = asyncio.create_task(_auto_start_engine())
    else:
        auto_task = None

    # Auto-start candle collector (writes candles to DB continuously)
    collector_task = asyncio.create_task(_auto_start_collector())

    # Auto-start strategy explorer if enabled
    auto_explore = os.getenv("AUTO_START_EXPLORER", "false").lower() == "true"
    explorer_task_bg = None
    if auto_explore:
        explorer_task_bg = asyncio.create_task(_auto_start_explorer())

    # Start paper position price updater (checks SL/TP every 10s)
    price_update_task = asyncio.create_task(_paper_price_update_loop())

    yield

    # Stop collector & explorer
    global _candle_collector, _strategy_explorer
    if _candle_collector:
        _candle_collector.stop()
    if _strategy_explorer:
        _strategy_explorer.stop()

    # Stop background tasks
    for task in [health_task, auto_task, db_retry_task, collector_task, explorer_task_bg, price_update_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    # Graceful shutdown
    logger.info("Initiating graceful shutdown...")
    if _engine_task and not _engine_task.done():
        logger.info("Stopping signal engine...")
        signal_engine.stop()
        try:
            await asyncio.wait_for(_engine_task, timeout=10)
        except asyncio.TimeoutError:
            logger.warning("Signal engine shutdown timeout")

    try:
        await data_provider.close()
    except Exception as e:
        logger.warning(f"Error closing data provider: {e}")
    try:
        await execution_engine.close_all()
    except Exception as e:
        logger.warning(f"Error closing execution engine: {e}")

    logger.info("App shutdown complete")


async def _connect_db_with_retry():
    """Connect to database with exponential backoff. Retries until success or shutdown."""
    global db_session
    from crypto_mega.data.models import init_db

    delays = [0, 5, 10, 20, 30, 60]  # seconds between attempts
    for attempt, delay in enumerate(delays):
        if delay > 0:
            logger.info(f"Database retry #{attempt + 1} in {delay}s...")
            await asyncio.sleep(delay)
        try:
            db_session = await asyncio.wait_for(init_db(config.db.url), timeout=15)
            logger.info(f"Database connected: {config.db.url[:30]}...")
            # Load paper tracker state from DB
            try:
                await paper_tracker.init_db(db_session)
            except Exception as e:
                logger.error(f"Failed to init paper tracker from DB: {e}")
            return
        except Exception as e:
            logger.warning(f"Database connection attempt #{attempt + 1} failed: {e}")

    # All retries exhausted
    add_system_alert(
        "error", "database",
        f"Could not connect to database after {len(delays)} attempts. "
        f"Check DATABASE_URL in Railway variables."
    )
    logger.error("Database connection failed permanently — app running without persistence")


async def _auto_start_collector():
    """Start CandleCollector as a background task once DB and exchange are ready."""
    global _candle_collector
    from crypto_mega.data.collector import CandleCollector

    # Wait for DB to be ready (up to 120s)
    for _ in range(120):
        if db_session is not None:
            break
        await asyncio.sleep(1)
    else:
        logger.warning("CandleCollector: DB not available, collector will not start")
        return

    # Wait for exchange to be ready (up to 120s)
    for _ in range(120):
        if data_provider._exchange is not None:
            break
        await asyncio.sleep(1)
    else:
        logger.warning("CandleCollector: exchange not connected, collector will not start")
        return

    _candle_collector = CandleCollector(
        session_factory=db_session,
        data_provider=data_provider,
        symbols=config.collector.symbols,
        timeframes=config.collector.timeframes,
        collect_interval=config.collector.interval_sec,
        candle_limit=config.collector.candle_limit,
        retention_days=config.collector.retention_days,
    )

    logger.info(
        f"CandleCollector auto-started | "
        f"symbols={config.collector.symbols} | "
        f"timeframes={config.collector.timeframes} | "
        f"interval={config.collector.interval_sec}s"
    )
    await _candle_collector.run_loop()


async def _auto_start_explorer():
    """Start StrategyExplorer as a background task once DB is ready."""
    global _strategy_explorer
    from crypto_mega.engine.explorer import StrategyExplorer

    # Wait for DB
    for _ in range(120):
        if db_session is not None:
            break
        await asyncio.sleep(1)
    else:
        logger.warning("StrategyExplorer: DB not available, will not start")
        return

    _strategy_explorer = StrategyExplorer(
        session_factory=db_session,
        config=config.exploration,
    )
    logger.info(
        f"StrategyExplorer auto-started | "
        f"exchanges={config.exploration.exchanges} | "
        f"symbols_per_exchange={config.exploration.symbols_per_exchange} | "
        f"queue_size={config.exploration.queue_size}"
    )
    await _strategy_explorer.run_loop()


async def _paper_price_update_loop():
    """Fetch live prices for open paper positions and check SL/TP every 10s."""
    await asyncio.sleep(10)  # Let the app boot
    logger.info("Paper price updater started")
    while True:
        try:
            symbols = paper_tracker.get_symbols_tracked()
            if symbols and data_provider._exchange is not None:
                for symbol in symbols:
                    try:
                        ticker = await data_provider.get_ticker(symbol)
                        price = ticker.get("last") or ticker.get("close")
                        if price:
                            closed = await paper_tracker.update_price(symbol, float(price))
                            if closed:
                                for pos in closed:
                                    await ws_manager.broadcast({
                                        "type": "position_closed",
                                        "position_id": pos.id,
                                        "symbol": pos.symbol,
                                        "reason": pos.close_reason,
                                        "pnl_pct": round(pos.realized_pnl_pct, 2),
                                    })
                    except Exception as e:
                        logger.debug(f"Price update failed for {symbol}: {e}")
        except Exception as e:
            logger.warning(f"Paper price update loop error: {e}")
        await asyncio.sleep(10)


async def periodic_health_check():
    """Log system health every N seconds. Detects problems and creates alerts."""
    while True:
        try:
            await asyncio.sleep(_health_check_interval)
            now = time.time()
            uptime = now - _app_start_time

            strategies_running = len(signal_engine._instances) if signal_engine._instances else 0
            ws_clients = len(ws_manager.active)
            db_status = "ok" if db_session else "none"
            exchange = data_provider._exchange_id or "none"

            logger.info(
                f"[HEALTH] uptime={uptime/60:.0f}min | "
                f"strategies={strategies_running} | "
                f"ws={ws_clients} | "
                f"db={db_status} | "
                f"exchange={exchange}"
            )

            # Check for engine crash
            if _engine_task and _engine_task.done():
                exc = _engine_task.exception() if not _engine_task.cancelled() else None
                add_system_alert(
                    "error", "engine",
                    f"Signal engine crashed! {exc or 'Task finished unexpectedly'}"
                )

            # Check data staleness (relative to timeframe)
            for key, df in data_provider._cache.items():
                if len(df) == 0:
                    continue
                last_ts = df["timestamp"].iloc[-1]
                if hasattr(last_ts, 'timestamp'):
                    age = now - last_ts.timestamp()
                else:
                    age = 0
                # Extract timeframe from key (e.g. "BTC/USDT_1h" -> "1h")
                parts = key.split("_")
                tf = parts[-1] if len(parts) > 1 else "1h"
                try:
                    tf_seconds = data_provider._timeframe_to_delta(tf).total_seconds()
                except Exception:
                    tf_seconds = 3600
                # Alert only if data is >2x the timeframe old (e.g. >2h for 1h candles)
                if age > tf_seconds * 2:
                    add_system_alert(
                        "warning", "data",
                        f"{key}: no new candle for {age/60:.0f}min (expected every {tf_seconds/60:.0f}min)"
                    )

        except Exception as e:
            logger.error(f"Health check error: {e}")


async def _auto_start_engine():
    """Auto-start engine after a brief delay (lets the app fully boot first)."""
    global _engine_task
    await asyncio.sleep(3)  # Wait for app to be ready
    logger.info("Auto-starting signal engine...")

    exchange = os.getenv("EXCHANGE_ID", "binance")
    symbols = os.getenv("SYMBOLS", "BTC/USDT,ETH/USDT")
    interval = float(os.getenv("ENGINE_INTERVAL", "60"))

    try:
        if data_provider._exchange is None:
            await data_provider.init_exchange(exchange, {"enableRateLimit": True})
            logger.info(f"Auto-start: connected to {data_provider._exchange_id}")

        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
        registered = strategy_loader.list_all()
        added = []
        for name, cls in registered.items():
            already = any(
                inst.strategy.name == name
                for inst in signal_engine._instances.values()
            )
            if already:
                continue
            cfg = StrategyConfig(
                name=name,
                symbols=symbol_list,
                timeframes=[TimeFrame.H1],
                priority=50,
            )
            strategy = cls(cfg)
            sid = signal_engine.add_strategy(strategy, cfg)
            resource_manager.set_allocation(sid, cfg.priority)
            paper_tracker.register_strategy(sid, name)
            added.append(name)

        _engine_task = asyncio.create_task(signal_engine.run_loop(interval))
        logger.info(
            f"Auto-started engine: {len(added)} strategies on {data_provider._exchange_id} | "
            f"symbols={symbol_list} | interval={interval}s"
        )
    except Exception as e:
        add_system_alert("error", "auto-start", f"Engine auto-start failed: {e}")
        logger.error(f"Auto-start failed: {e}")


app = FastAPI(
    title="CryptoMega",
    version="0.1.0",
    description="Massive crypto trading signal system",
    lifespan=lifespan,
)


# ─── Signal broadcast hook ───

async def broadcast_signal(signal: Signal):
    """Broadcast signals to all WebSocket clients."""
    await ws_manager.broadcast({
        "type": "signal",
        "data": {
            "id": signal.id,
            "strategy_id": signal.strategy_id[:8],
            "symbol": signal.symbol,
            "direction": signal.direction.value,
            "strength": signal.strength,
            "price": signal.price,
            "timestamp": str(signal.timestamp),
        },
    })

signal_engine.on_signal(broadcast_signal)
signal_engine.on_signal(paper_tracker.handle_signal)


# ─── Request/Response models ───

class StrategyCodeRequest(BaseModel):
    code: str
    name: str = "dynamic"
    description: str = ""
    symbols: list[str] = ["BTC/USDT"]
    timeframes: list[str] = ["1h"]
    parameters: dict[str, Any] = {}
    priority: int = 50
    auto_execute: bool = False


class StrategyFileRequest(BaseModel):
    filepath: str


class PriorityRequest(BaseModel):
    strategy_id: str
    priority: int


class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: list[str] = ["BTC/USDT"]
    timeframes: list[str] = ["1h"]
    parameters: dict[str, Any] = {}
    param_grid: dict[str, list] | None = None
    max_combinations: int | None = None
    initial_capital: float = 10000.0
    async_mode: bool = False  # if True, run via Celery


class ExecuteSignalRequest(BaseModel):
    signal_index: int
    exchange_id: str | None = None


class ApproveAdjustmentRequest(BaseModel):
    index: int


class ExchangeConnectRequest(BaseModel):
    exchange_id: str = "binance"
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True


# ─── WebSocket endpoints ───

@app.websocket("/ws/signals")
async def websocket_signals(ws: WebSocket):
    """
    Real-time signal stream via WebSocket.
    Connect with: ws://host:port/ws/signals
    Receives JSON messages with type="signal" for every new signal.
    """
    await ws_manager.connect(ws)
    try:
        while True:
            # Client can send commands (e.g., filter symbols, pause)
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": time.time()})
                elif msg.get("type") == "status":
                    await ws.send_json({
                        "type": "status",
                        "data": signal_engine.get_status(),
                    })
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.websocket("/ws/monitor")
async def websocket_monitor(ws: WebSocket):
    """
    Real-time monitoring stream.
    Pushes performance stats every 5 seconds.
    """
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.send_json({
                "type": "monitor",
                "data": {
                    "strategies": monitor.get_all_stats(),
                    "risk": risk_manager.get_status(),
                    "resources": resource_manager.get_status(),
                    "alerts": monitor.get_alerts(limit=10),
                },
            })
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ─── Strategy endpoints ───

@app.post("/strategies/load-code")
async def load_strategy_from_code(req: StrategyCodeRequest):
    """Load a strategy from code string (the Vasya/GPT interface)."""
    classes = strategy_loader.load_from_code(req.code, req.name)
    if not classes:
        raise HTTPException(400, "No valid strategy classes found in code")

    # Persist to DB
    if db_session:
        from crypto_mega.data.models import StrategyRecord
        async with db_session() as session:
            for cls in classes:
                record = StrategyRecord(
                    name=req.name,
                    description=req.description,
                    code=req.code,
                    symbols=json.dumps(req.symbols),
                    timeframes=",".join(req.timeframes),
                    parameters=json.dumps(req.parameters),
                    priority=req.priority,
                    auto_execute=req.auto_execute,
                    status="running",
                )
                session.add(record)
            await session.commit()

    results = []
    for cls in classes:
        cfg = StrategyConfig(
            name=req.name,
            description=req.description,
            symbols=req.symbols,
            timeframes=[TimeFrame(tf) for tf in req.timeframes],
            parameters=req.parameters,
            priority=req.priority,
            auto_execute=req.auto_execute,
        )
        strategy = cls(cfg)
        sid = signal_engine.add_strategy(strategy, cfg)
        resource_manager.set_allocation(sid, req.priority)
        results.append({"id": sid, "name": cls.__name__, "status": "loaded"})

    # Broadcast to WebSocket clients
    await ws_manager.broadcast({"type": "strategy_loaded", "data": results})

    return {"strategies": results}


@app.post("/strategies/load-file")
async def load_strategy_from_file(req: StrategyFileRequest):
    """Load strategy from a .py file."""
    classes = strategy_loader.load_from_file(req.filepath)
    if not classes:
        raise HTTPException(400, "No valid strategy classes found in file")
    return {"loaded": [cls.__name__ for cls in classes]}


@app.post("/strategies/load-directory")
async def load_strategies_from_dir(directory: str = "strategies_user"):
    """Scan directory and load all strategies."""
    classes = strategy_loader.load_directory(directory)
    return {"loaded": [cls.__name__ for cls in classes]}


@app.get("/strategies")
async def list_strategies():
    """List all registered strategies with full metadata."""
    from crypto_mega.utils.types import StrategyConfig

    registered = {}
    for name, cls in strategy_loader.list_all().items():
        try:
            dummy_cfg = StrategyConfig(name=name)
            instance = cls(dummy_cfg)
            registered[name] = instance.describe()
        except Exception:
            registered[name] = {"name": name, "description": "", "category": "custom"}

    return {
        "registered": registered,
        "running": signal_engine.get_status(),
    }


@app.post("/strategies/{strategy_id}/pause")
async def pause_strategy(strategy_id: str):
    signal_engine.pause_strategy(strategy_id)
    return {"status": "paused"}


@app.post("/strategies/{strategy_id}/resume")
async def resume_strategy(strategy_id: str):
    signal_engine.resume_strategy(strategy_id)
    return {"status": "resumed"}


@app.delete("/strategies/{strategy_id}")
async def remove_strategy(strategy_id: str):
    signal_engine.remove_strategy(strategy_id)
    resource_manager.remove_allocation(strategy_id)
    return {"status": "removed"}


@app.get("/strategies/templates")
async def get_strategy_templates():
    """Return strategy code templates for batch generation."""
    return {"templates": STRATEGY_TEMPLATES}


STRATEGY_TEMPLATES = {
    "sma_crossover": {
        "label": "SMA Crossover",
        "category": "trend",
        "description": "Two moving averages — buy on golden cross, sell on death cross",
        "code": '''import pandas as pd
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig

class {class_name}(BaseStrategy):
    """{description}"""
    DESCRIPTION = "{description}"
    CATEGORY = "trend"
    RISK_LEVEL = "{risk_level}"
    BEST_TIMEFRAMES = {timeframes}
    BEST_MARKETS = ["trending"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.fast_period = config.parameters.get("fast_period", {fast_period})
        self.slow_period = config.parameters.get("slow_period", {slow_period})

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []
        for key, df in data.items():
            if len(df) < self.slow_period + 2:
                continue
            symbol = key.split("_")[0]
            df = df.copy()
            df["sma_fast"] = df["close"].rolling(self.fast_period).mean()
            df["sma_slow"] = df["close"].rolling(self.slow_period).mean()
            df = df.dropna()
            if len(df) < 2:
                continue
            prev, curr = df.iloc[-2], df.iloc[-1]
            if prev["sma_fast"] <= prev["sma_slow"] and curr["sma_fast"] > curr["sma_slow"]:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.LONG,
                    strength=0.7, price=curr["close"],
                    stop_loss=curr["close"] * {sl_long}, take_profit=curr["close"] * {tp_long}))
            elif prev["sma_fast"] >= prev["sma_slow"] and curr["sma_fast"] < curr["sma_slow"]:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.SHORT,
                    strength=0.7, price=curr["close"],
                    stop_loss=curr["close"] * {sl_short}, take_profit=curr["close"] * {tp_short}))
        return signals

    def param_grid(self):
        return {{"fast_period": [5, 8, 10, 15, 20], "slow_period": [20, 30, 50, 100]}}
    def param_defaults(self):
        return {{"fast_period": {fast_period}, "slow_period": {slow_period}}}
''',
        "params": {
            "class_name": {"default": "SMACross", "label": "Class name"},
            "description": {"default": "SMA crossover strategy", "label": "Description"},
            "fast_period": {"default": 10, "label": "Fast SMA period", "type": "int"},
            "slow_period": {"default": 30, "label": "Slow SMA period", "type": "int"},
            "sl_long": {"default": 0.98, "label": "Stop-loss % (long)", "type": "float"},
            "tp_long": {"default": 1.04, "label": "Take-profit % (long)", "type": "float"},
            "sl_short": {"default": 1.02, "label": "Stop-loss % (short)", "type": "float"},
            "tp_short": {"default": 0.96, "label": "Take-profit % (short)", "type": "float"},
            "risk_level": {"default": "low", "label": "Risk level", "type": "select", "options": ["low", "medium", "high"]},
            "timeframes": {"default": '["1h", "4h"]', "label": "Timeframes", "type": "text"},
        },
    },
    "rsi_reversion": {
        "label": "RSI Mean-Reversion",
        "category": "mean-reversion",
        "description": "Buy oversold RSI, sell overbought RSI with Bollinger Band confirmation",
        "code": '''import numpy as np
import pandas as pd
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig

class {class_name}(BaseStrategy):
    """{description}"""
    DESCRIPTION = "{description}"
    CATEGORY = "mean-reversion"
    RISK_LEVEL = "{risk_level}"
    BEST_TIMEFRAMES = {timeframes}
    BEST_MARKETS = ["ranging", "sideways"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.rsi_period = config.parameters.get("rsi_period", {rsi_period})
        self.rsi_oversold = config.parameters.get("rsi_oversold", {rsi_oversold})
        self.rsi_overbought = config.parameters.get("rsi_overbought", {rsi_overbought})
        self.bb_period = config.parameters.get("bb_period", {bb_period})
        self.bb_std = config.parameters.get("bb_std", {bb_std})

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []
        for key, df in data.items():
            if len(df) < max(self.rsi_period, self.bb_period) + 5:
                continue
            symbol = key.split("_")[0]
            df = df.copy()
            delta = df["close"].diff()
            gain = delta.clip(lower=0).rolling(self.rsi_period).mean()
            loss = (-delta.clip(upper=0)).rolling(self.rsi_period).mean()
            rs = gain / loss.replace(0, np.nan)
            df["rsi"] = 100 - (100 / (1 + rs))
            df["bb_mid"] = df["close"].rolling(self.bb_period).mean()
            bb_s = df["close"].rolling(self.bb_period).std()
            df["bb_upper"] = df["bb_mid"] + self.bb_std * bb_s
            df["bb_lower"] = df["bb_mid"] - self.bb_std * bb_s
            df = df.dropna()
            if len(df) < 1:
                continue
            last = df.iloc[-1]
            if last["rsi"] < self.rsi_oversold and last["close"] <= last["bb_lower"]:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.LONG,
                    strength=min(1.0, (self.rsi_oversold - last["rsi"])/30 + 0.5),
                    price=last["close"], stop_loss=last["close"]*0.97, take_profit=last["bb_mid"]))
            elif last["rsi"] > self.rsi_overbought and last["close"] >= last["bb_upper"]:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.SHORT,
                    strength=min(1.0, (last["rsi"] - self.rsi_overbought)/30 + 0.5),
                    price=last["close"], stop_loss=last["close"]*1.03, take_profit=last["bb_mid"]))
        return signals

    def param_grid(self):
        return {{"rsi_period": [7, 14, 21], "bb_period": [15, 20, 25], "bb_std": [1.5, 2.0, 2.5]}}
    def param_defaults(self):
        return {{"rsi_period": {rsi_period}, "bb_period": {bb_period}, "bb_std": {bb_std}}}
''',
        "params": {
            "class_name": {"default": "RSIMeanRev", "label": "Class name"},
            "description": {"default": "RSI + Bollinger mean-reversion", "label": "Description"},
            "rsi_period": {"default": 14, "label": "RSI period", "type": "int"},
            "rsi_oversold": {"default": 30, "label": "RSI oversold", "type": "int"},
            "rsi_overbought": {"default": 70, "label": "RSI overbought", "type": "int"},
            "bb_period": {"default": 20, "label": "BB period", "type": "int"},
            "bb_std": {"default": 2.0, "label": "BB std dev", "type": "float"},
            "risk_level": {"default": "medium", "label": "Risk level", "type": "select", "options": ["low", "medium", "high"]},
            "timeframes": {"default": '["15m", "1h"]', "label": "Timeframes", "type": "text"},
        },
    },
    "ema_momentum": {
        "label": "EMA Momentum",
        "category": "momentum",
        "description": "EMA slope + volume spike = momentum entry",
        "code": '''import pandas as pd
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig

class {class_name}(BaseStrategy):
    """{description}"""
    DESCRIPTION = "{description}"
    CATEGORY = "momentum"
    RISK_LEVEL = "{risk_level}"
    BEST_TIMEFRAMES = {timeframes}
    BEST_MARKETS = ["trending", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.ema_period = config.parameters.get("ema_period", {ema_period})
        self.slope_bars = config.parameters.get("slope_bars", {slope_bars})
        self.vol_mult = config.parameters.get("vol_mult", {vol_mult})

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []
        for key, df in data.items():
            if len(df) < self.ema_period + self.slope_bars + 5:
                continue
            symbol = key.split("_")[0]
            df = df.copy()
            df["ema"] = df["close"].ewm(span=self.ema_period).mean()
            slope = df["ema"].iloc[-1] - df["ema"].iloc[-self.slope_bars]
            avg_vol = df["volume"].rolling(20).mean().iloc[-1]
            curr_vol = df["volume"].iloc[-1]
            if curr_vol < avg_vol * self.vol_mult:
                continue
            price = df["close"].iloc[-1]
            strength = min(1.0, abs(slope) / price * 100)
            if slope > 0:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.LONG,
                    strength=strength, price=price,
                    stop_loss=price * {sl_long}, take_profit=price * {tp_long}))
            elif slope < 0:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.SHORT,
                    strength=strength, price=price,
                    stop_loss=price * {sl_short}, take_profit=price * {tp_short}))
        return signals

    def param_grid(self):
        return {{"ema_period": [10, 15, 20, 30], "slope_bars": [2, 3, 5], "vol_mult": [1.2, 1.5, 2.0]}}
    def param_defaults(self):
        return {{"ema_period": {ema_period}, "slope_bars": {slope_bars}, "vol_mult": {vol_mult}}}
''',
        "params": {
            "class_name": {"default": "EMAMomentum", "label": "Class name"},
            "description": {"default": "EMA momentum with volume confirmation", "label": "Description"},
            "ema_period": {"default": 20, "label": "EMA period", "type": "int"},
            "slope_bars": {"default": 3, "label": "Slope lookback bars", "type": "int"},
            "vol_mult": {"default": 1.5, "label": "Volume multiplier", "type": "float"},
            "sl_long": {"default": 0.97, "label": "Stop-loss (long)", "type": "float"},
            "tp_long": {"default": 1.06, "label": "Take-profit (long)", "type": "float"},
            "sl_short": {"default": 1.03, "label": "Stop-loss (short)", "type": "float"},
            "tp_short": {"default": 0.94, "label": "Take-profit (short)", "type": "float"},
            "risk_level": {"default": "medium", "label": "Risk level", "type": "select", "options": ["low", "medium", "high"]},
            "timeframes": {"default": '["1h", "4h"]', "label": "Timeframes", "type": "text"},
        },
    },
    "breakout": {
        "label": "Channel Breakout",
        "category": "breakout",
        "description": "Enters on price breaking N-bar high/low channel with volume",
        "code": '''import pandas as pd
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig

class {class_name}(BaseStrategy):
    """{description}"""
    DESCRIPTION = "{description}"
    CATEGORY = "breakout"
    RISK_LEVEL = "{risk_level}"
    BEST_TIMEFRAMES = {timeframes}
    BEST_MARKETS = ["consolidating", "volatile"]

    def __init__(self, config: StrategyConfig):
        super().__init__(config)
        self.lookback = config.parameters.get("lookback", {lookback})
        self.vol_mult = config.parameters.get("vol_mult", {vol_mult})

    def generate_signals(self, data: dict[str, pd.DataFrame]) -> list[Signal]:
        signals = []
        for key, df in data.items():
            if len(df) < self.lookback + 5:
                continue
            symbol = key.split("_")[0]
            df = df.copy()
            window = df.iloc[-(self.lookback+1):-1]
            ch_high = window["high"].max()
            ch_low = window["low"].min()
            last = df.iloc[-1]
            avg_vol = df["volume"].rolling(20).mean().iloc[-1]
            if last["volume"] < avg_vol * self.vol_mult:
                continue
            if last["close"] > ch_high:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.LONG,
                    strength=0.8, price=last["close"],
                    stop_loss=ch_low, take_profit=last["close"] + (ch_high - ch_low)))
            elif last["close"] < ch_low:
                signals.append(Signal(symbol=symbol, direction=SignalDirection.SHORT,
                    strength=0.8, price=last["close"],
                    stop_loss=ch_high, take_profit=last["close"] - (ch_high - ch_low)))
        return signals

    def param_grid(self):
        return {{"lookback": [10, 20, 30, 50], "vol_mult": [1.2, 1.5, 2.0]}}
    def param_defaults(self):
        return {{"lookback": {lookback}, "vol_mult": {vol_mult}}}
''',
        "params": {
            "class_name": {"default": "ChannelBreak", "label": "Class name"},
            "description": {"default": "Channel breakout with volume confirmation", "label": "Description"},
            "lookback": {"default": 20, "label": "Channel lookback bars", "type": "int"},
            "vol_mult": {"default": 1.5, "label": "Volume multiplier", "type": "float"},
            "risk_level": {"default": "high", "label": "Risk level", "type": "select", "options": ["low", "medium", "high"]},
            "timeframes": {"default": '["1h", "4h"]', "label": "Timeframes", "type": "text"},
        },
    },
}


# ─── Resource management endpoints ───

@app.get("/resources")
async def get_resources():
    return resource_manager.get_status()


@app.post("/resources/priority")
async def set_priority(req: PriorityRequest):
    resource_manager.set_allocation(req.strategy_id, req.priority)
    return {"status": "updated"}


@app.get("/resources/adjustments")
async def get_pending_adjustments():
    return {"adjustments": resource_manager.get_pending_adjustments()}


@app.post("/resources/adjustments/approve")
async def approve_adjustment(req: ApproveAdjustmentRequest):
    resource_manager.approve_adjustment(req.index)
    return {"status": "approved"}


# ─── Backtesting endpoints ───

@app.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """Run backtest — sync or via Celery (async_mode=true)."""
    cls = strategy_loader.get(req.strategy_name)
    if not cls:
        raise HTTPException(404, f"Strategy not found: {req.strategy_name}")

    # Async mode — dispatch to Celery worker
    if req.async_mode:
        from crypto_mega.engine.tasks import run_backtest_task, run_grid_search_task

        if req.param_grid:
            task = run_grid_search_task.delay(
                req.strategy_name, req.symbols, req.timeframes,
                req.param_grid, req.max_combinations, req.initial_capital,
            )
        else:
            task = run_backtest_task.delay(
                req.strategy_name, req.symbols, req.timeframes,
                req.parameters, req.initial_capital,
            )
        return {"task_id": task.id, "status": "submitted"}

    # Sync mode
    cfg = StrategyConfig(
        name=req.strategy_name,
        symbols=req.symbols,
        timeframes=[TimeFrame(tf) for tf in req.timeframes],
        parameters=req.parameters,
    )

    data = await data_provider.fetch_multi(req.symbols, req.timeframes, limit=500)
    bt = Backtester(initial_capital=req.initial_capital)

    if req.param_grid:
        results = bt.grid_search(cls, data, cfg, req.param_grid, req.max_combinations)
        return {
            "type": "grid_search",
            "total_combinations": len(results),
            "top_10": [
                {
                    "params": r.parameters,
                    "pnl": round(r.total_pnl, 2),
                    "pnl_pct": round(r.total_pnl_pct, 2),
                    "trades": r.total_trades,
                    "win_rate": round(r.win_rate, 1),
                    "sharpe": round(r.sharpe_ratio, 2),
                    "max_dd": round(r.max_drawdown, 2),
                    "profit_factor": round(r.profit_factor, 2),
                }
                for r in results[:10]
            ],
        }
    else:
        strategy = cls(cfg)
        result = bt.run(strategy, data, cfg)
        return {
            "type": "single_run",
            "pnl": round(result.total_pnl, 2),
            "pnl_pct": round(result.total_pnl_pct, 2),
            "trades": result.total_trades,
            "win_rate": round(result.win_rate, 1),
            "sharpe": round(result.sharpe_ratio, 2),
            "max_dd": round(result.max_drawdown, 2),
            "profit_factor": round(result.profit_factor, 2),
            "run_time": round(result.run_time_sec, 3),
        }


@app.get("/backtest/task/{task_id}")
async def get_backtest_task_status(task_id: str):
    """Check status of an async backtest task."""
    from crypto_mega.engine.tasks import celery_app
    result = celery_app.AsyncResult(task_id)
    response = {"task_id": task_id, "status": result.state}
    if result.ready():
        response["result"] = result.result
    return response


# ─── Execution endpoints ───

@app.get("/execution/pending")
async def get_pending_signals():
    return {"signals": execution_engine.get_pending_signals()}


@app.post("/execution/approve")
async def approve_signal(req: ExecuteSignalRequest):
    result = await execution_engine.approve_and_execute(req.signal_index, req.exchange_id)
    if result:
        return {"status": "executed", "order_id": result.exchange_order_id}
    raise HTTPException(400, "Invalid signal index")


@app.post("/execution/approve-strategy/{strategy_id}")
async def approve_strategy_execution(strategy_id: str):
    execution_engine.approve_strategy_for_execution(strategy_id)
    return {"status": "approved"}


@app.get("/execution/trades")
async def get_trades():
    return {"trades": execution_engine.get_executed_trades()}


# ─── Monitoring endpoints ───

@app.get("/monitor/stats")
async def get_monitor_stats():
    return {
        "strategies": monitor.get_all_stats(),
        "recommendations": monitor.get_recommendations(),
    }


@app.get("/monitor/alerts")
async def get_alerts(severity: str | None = None):
    return {"alerts": monitor.get_alerts(severity)}


# ─── Risk management endpoints ───

@app.get("/risk")
async def get_risk_status():
    return risk_manager.get_status()


@app.post("/risk/kill-switch/activate")
async def activate_kill_switch():
    risk_manager.activate_kill_switch()
    await ws_manager.broadcast({"type": "kill_switch", "data": {"active": True}})
    return {"status": "KILL SWITCH ACTIVATED"}


@app.post("/risk/kill-switch/deactivate")
async def deactivate_kill_switch():
    risk_manager.deactivate_kill_switch()
    await ws_manager.broadcast({"type": "kill_switch", "data": {"active": False}})
    return {"status": "kill switch deactivated"}


# ─── Paper tracker endpoints ───

@app.get("/paper/leaderboard")
async def paper_leaderboard(sort_by: str = "total_pnl_pct", limit: int = 50):
    """Strategy leaderboard based on paper trading results."""
    return {"leaderboard": paper_tracker.get_leaderboard(sort_by, limit)}


@app.get("/paper/positions/open")
async def paper_positions_open(strategy_id: str | None = None):
    return {"positions": paper_tracker.get_open_positions(strategy_id)}


@app.post("/paper/reset")
async def paper_reset():
    """Reset all paper positions and signals."""
    result = await paper_tracker.reset_all()
    return result


@app.post("/paper/deduplicate")
async def paper_deduplicate():
    """Remove duplicate open positions, keeping oldest per strategy+symbol+direction."""
    removed = await paper_tracker.deduplicate_positions()
    return {"removed": removed}


@app.get("/paper/positions/closed")
async def paper_positions_closed(strategy_id: str | None = None, limit: int = 100):
    return {"positions": paper_tracker.get_closed_positions(strategy_id, limit)}


@app.get("/paper/signals")
async def paper_signals(limit: int = 100):
    return {"signals": paper_tracker.get_signal_log(limit)}


@app.get("/paper/signal/{signal_id}")
async def paper_signal_detail(signal_id: str):
    """Get full detail for a single signal including metadata & candles."""
    for s in paper_tracker._signal_log:
        if s["id"] == signal_id:
            return s
    raise HTTPException(404, "Signal not found")


@app.get("/paper/position/{position_id}")
async def paper_position_detail(position_id: str):
    """Get full detail for a single position including signal metadata."""
    # Check open positions
    pos = paper_tracker._positions.get(position_id)
    if pos:
        return {
            "id": pos.id,
            "signal_id": pos.signal_id,
            "strategy_id": pos.strategy_id[:8],
            "strategy_name": pos.strategy_name,
            "symbol": pos.symbol,
            "direction": pos.direction.value,
            "entry_price": pos.entry_price,
            "current_price": pos.current_price,
            "unrealized_pnl_pct": round(pos.unrealized_pnl_pct, 2),
            "stop_loss": pos.stop_loss,
            "take_profit": pos.take_profit,
            "strength": pos.signal_strength,
            "opened_at": str(pos.opened_at),
            "metadata": pos.signal_metadata,
        }
    # Check closed positions
    for p in paper_tracker._closed:
        if p.id == position_id:
            return {
                "id": p.id,
                "signal_id": p.signal_id,
                "strategy_id": p.strategy_id[:8],
                "strategy_name": p.strategy_name,
                "symbol": p.symbol,
                "direction": p.direction.value,
                "entry_price": p.entry_price,
                "exit_price": p.exit_price,
                "realized_pnl_pct": round(p.realized_pnl_pct, 2),
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "strength": p.signal_strength,
                "close_reason": p.close_reason,
                "opened_at": str(p.opened_at),
                "closed_at": str(p.closed_at),
                "metadata": p.signal_metadata,
            }
    raise HTTPException(404, "Position not found")


@app.get("/paper/stats/{strategy_id}")
async def paper_stats(strategy_id: str):
    """Detailed paper trading stats for a strategy including positions and signals."""
    # Find full strategy ID from prefix — check engine first, then paper tracker
    full_id = None
    for sid in list(signal_engine._instances.keys()):
        if sid.startswith(strategy_id):
            full_id = sid
            break
    if not full_id:
        # Also check paper tracker positions/closed for strategies not currently running
        for p in list(paper_tracker._positions.values()) + paper_tracker._closed:
            if p.strategy_id.startswith(strategy_id):
                full_id = p.strategy_id
                break
    if not full_id:
        raise HTTPException(404, "Strategy not found")

    stats = paper_tracker.get_strategy_stats(full_id)
    result = stats.to_dict()
    # Include recent positions and signals for this strategy
    result["open_positions_list"] = paper_tracker.get_open_positions(full_id)
    result["closed_positions_list"] = paper_tracker.get_closed_positions(full_id, limit=50)
    result["recent_signals"] = [
        s for s in paper_tracker.get_signal_log(500)
        if s.get("strategy_id") == full_id[:8]
    ][-50:]
    return result


@app.post("/paper/promote/{strategy_id}")
async def promote_strategy_to_live(strategy_id: str):
    """Promote a strategy to live trading (auto-execute signals)."""
    full_id = None
    for sid in list(signal_engine._instances.keys()):
        if sid.startswith(strategy_id):
            full_id = sid
            break
    if not full_id:
        raise HTTPException(404, "Strategy not found")

    execution_engine.approve_strategy_for_execution(full_id)
    return {"status": "promoted", "strategy_id": full_id[:8], "message": "Signals will now be forwarded to exchange"}


# ─── Engine control endpoints ───

@app.post("/engine/start")
async def start_engine(
    interval: float = 60.0,
    symbols: str = "BTC/USDT,ETH/USDT",
    exchange: str = os.getenv("EXCHANGE_ID", "binance"),
):
    """Start the signal engine loop.

    This does everything needed in one call:
    1. Init exchange connection for data (if not already connected)
    2. Instantiate all registered strategies and add to engine
    3. Register them in paper tracker
    4. Start the signal generation loop
    """
    global _engine_task
    if _engine_task and not _engine_task.done():
        return {"status": "already_running", "strategies": len(signal_engine._instances)}

    # 1. Init exchange for live data
    if data_provider._exchange is None:
        try:
            await data_provider.init_exchange(exchange, {"enableRateLimit": True})
            logger.info(f"Data provider connected to {exchange}")
        except Exception as e:
            logger.warning(f"Could not connect to {exchange}: {e}")
            return {"status": "error", "message": f"Exchange connection failed: {e}"}

    # 2. Parse symbols
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

    # 3. Instantiate all registered strategies and add to engine
    registered = strategy_loader.list_all()
    added = []
    for name, cls in registered.items():
        # Skip if already running
        already_running = any(
            inst.strategy.name == name
            for inst in signal_engine._instances.values()
        )
        if already_running:
            continue

        cfg = StrategyConfig(
            name=name,
            symbols=symbol_list,
            timeframes=[TimeFrame.H1],
            priority=50,
        )
        try:
            strategy = cls(cfg)
            sid = signal_engine.add_strategy(strategy, cfg)
            resource_manager.set_allocation(sid, cfg.priority)
            paper_tracker.register_strategy(sid, name)
            added.append({"id": sid[:8], "name": name})
        except Exception as e:
            logger.error(f"Failed to instantiate {name}: {e}")

    # 4. Start the loop
    _engine_task = asyncio.create_task(signal_engine.run_loop(interval))

    return {
        "status": "started",
        "interval": interval,
        "exchange": exchange,
        "symbols": symbol_list,
        "strategies_added": added,
        "total_running": len(signal_engine._instances),
    }


@app.post("/engine/stop")
async def stop_engine():
    """Stop the signal engine loop."""
    global _engine_task
    signal_engine.stop()
    if _engine_task and not _engine_task.done():
        _engine_task.cancel()
    _engine_task = None
    return {"status": "stopped"}


# ─── Exchange connection endpoint ───

@app.post("/exchange/connect")
async def connect_exchange(req: ExchangeConnectRequest):
    """Connect to a crypto exchange via ccxt."""
    try:
        conn = ExchangeConnection(
            exchange_id=req.exchange_id,
            api_key=req.api_key,
            api_secret=req.api_secret,
            sandbox=req.sandbox,
        )
        await execution_engine.add_exchange(conn)
        return {"status": "connected", "exchange": req.exchange_id, "sandbox": req.sandbox}
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")


@app.get("/exchange/symbols")
async def exchange_symbols(exchange: str = ""):
    """Get all trading pairs from an exchange, grouped by quote currency.

    Always respects the `exchange` param — connects temporarily if needed.
    Returns symbols grouped by quote (USDT, BTC, ETH, etc.) with counts.
    """
    ex_id = exchange or os.getenv("EXCHANGE_ID", "binance")

    # If requested exchange matches current data_provider, reuse it
    if (
        data_provider._exchange is not None
        and (data_provider._exchange_id or "").lower() == ex_id.lower()
    ):
        try:
            all_symbols = await data_provider.get_available_symbols()
            return _group_symbols(all_symbols, data_provider._exchange_id or ex_id)
        except Exception as e:
            logger.warning(f"Failed to fetch symbols from {ex_id}: {e}")

    # Otherwise connect temporarily to the requested exchange
    try:
        temp = DataProvider()
        await temp.init_exchange(ex_id, {"enableRateLimit": True})
        all_symbols = await temp.get_available_symbols()
        await temp.close()
        return _group_symbols(all_symbols, ex_id)
    except Exception as e:
        raise HTTPException(503, f"Cannot fetch symbols from {ex_id}: {e}")


def _group_symbols(all_symbols: list[str], exchange_name: str) -> dict:
    """Group symbols by quote currency (USDT, BTC, ETH, etc.)."""
    by_quote: dict[str, list[str]] = {}
    for s in sorted(all_symbols):
        if "/" not in s:
            continue
        _, quote = s.split("/", 1)
        by_quote.setdefault(quote, []).append(s)
    # Sort groups by count (most popular first)
    sorted_groups = dict(sorted(by_quote.items(), key=lambda x: -len(x[1])))
    return {
        "exchange": exchange_name,
        "by_quote": sorted_groups,
        "quotes": list(sorted_groups.keys()),
        "total": sum(len(v) for v in sorted_groups.values()),
    }


# ─── Logs ───

@app.get("/data/collector/status")
async def collector_status():
    """Status of the background CandleCollector."""
    if _candle_collector is None:
        return {"running": False, "message": "Collector not started yet (waiting for DB + exchange)"}
    return _candle_collector.get_stats()


@app.get("/data/health")
async def data_health():
    """Data integrity status — candle freshness, gaps, errors."""
    return {"data": data_provider.get_data_health()}


@app.get("/data/candles/summary")
async def candles_summary():
    """Aggregated summary of all candle data in the database."""
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from sqlalchemy import select, func as sa_func, distinct
    from crypto_mega.data.models import CandleRecord

    async with db_session() as session:
        # Get all unique symbol+timeframe combos with stats
        stmt = (
            select(
                CandleRecord.symbol,
                CandleRecord.timeframe,
                sa_func.count(CandleRecord.id).label("count"),
                sa_func.min(CandleRecord.timestamp_ms).label("first_ts"),
                sa_func.max(CandleRecord.timestamp_ms).label("last_ts"),
                sa_func.min(CandleRecord.collected_at).label("first_collected"),
                sa_func.max(CandleRecord.collected_at).label("last_collected"),
            )
            .group_by(CandleRecord.symbol, CandleRecord.timeframe)
            .order_by(CandleRecord.symbol, CandleRecord.timeframe)
        )
        rows = (await session.execute(stmt)).all()

        # Total candle count
        total_stmt = select(sa_func.count(CandleRecord.id))
        total_count = (await session.execute(total_stmt)).scalar() or 0

        # Distinct symbols and timeframes
        symbols_stmt = select(distinct(CandleRecord.symbol))
        symbols = [r[0] for r in (await session.execute(symbols_stmt)).all()]

        timeframes_stmt = select(distinct(CandleRecord.timeframe))
        timeframes = [r[0] for r in (await session.execute(timeframes_stmt)).all()]

        # Get last_checked times from collector stats (when we last fetched, regardless of data change)
        collector_pairs = {}
        if _candle_collector:
            collector_pairs = _candle_collector.get_stats().get("pairs", {})

        series = []
        for row in rows:
            key = f"{row.symbol}_{row.timeframe}"
            pair_stats = collector_pairs.get(key, {})
            series.append({
                "symbol": row.symbol,
                "timeframe": row.timeframe,
                "candle_count": row.count,
                "first_timestamp_ms": row.first_ts,
                "last_timestamp_ms": row.last_ts,
                "first_collected": row.first_collected.isoformat() if row.first_collected else None,
                "last_collected": row.last_collected.isoformat() if row.last_collected else None,
                "last_checked": pair_stats.get("last_collect"),
            })

    return {
        "total_candles": total_count,
        "symbols": symbols,
        "timeframes": timeframes,
        "series": series,
    }


@app.get("/data/candles/check-gaps")
async def candles_check_gaps(symbol: str = "", timeframe: str = ""):
    """Check for missing candles (gaps) in stored data sequences."""
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from sqlalchemy import select, func as sa_func, distinct
    from crypto_mega.data.models import CandleRecord

    TIMEFRAME_MS = {
        "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
        "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000,
        "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000,
        "12h": 43_200_000, "1d": 86_400_000, "3d": 259_200_000,
        "1w": 604_800_000,
    }

    async with db_session() as session:
        # Determine which series to check
        if symbol and timeframe:
            pairs = [(symbol, timeframe)]
        else:
            stmt = (
                select(distinct(CandleRecord.symbol), CandleRecord.timeframe)
                .group_by(CandleRecord.symbol, CandleRecord.timeframe)
            )
            pairs = [(r[0], r[1]) for r in (await session.execute(stmt)).all()]

        results = []
        for sym, tf in pairs:
            step_ms = TIMEFRAME_MS.get(tf)
            if not step_ms:
                results.append({
                    "symbol": sym, "timeframe": tf,
                    "error": f"Unknown timeframe: {tf}",
                })
                continue

            # Fetch all timestamps sorted
            ts_stmt = (
                select(CandleRecord.timestamp_ms)
                .where(CandleRecord.symbol == sym, CandleRecord.timeframe == tf)
                .order_by(CandleRecord.timestamp_ms)
            )
            timestamps = [r[0] for r in (await session.execute(ts_stmt)).all()]

            if len(timestamps) < 2:
                results.append({
                    "symbol": sym, "timeframe": tf,
                    "total_candles": len(timestamps),
                    "gaps": [],
                    "missing_count": 0,
                    "status": "insufficient_data",
                })
                continue

            # Find gaps
            gaps = []
            total_missing = 0
            for i in range(1, len(timestamps)):
                diff = timestamps[i] - timestamps[i - 1]
                if diff > step_ms * 1.5:  # allow 50% tolerance for exchange quirks
                    missing = int(diff / step_ms) - 1
                    total_missing += missing
                    gaps.append({
                        "after_ms": timestamps[i - 1],
                        "before_ms": timestamps[i],
                        "missing_candles": missing,
                        "gap_duration_min": round(diff / 60_000, 1),
                    })

            # Duplicates check
            dupe_stmt = (
                select(CandleRecord.timestamp_ms, sa_func.count(CandleRecord.id))
                .where(CandleRecord.symbol == sym, CandleRecord.timeframe == tf)
                .group_by(CandleRecord.timestamp_ms)
                .having(sa_func.count(CandleRecord.id) > 1)
            )
            dupes = (await session.execute(dupe_stmt)).all()

            status = "ok"
            if total_missing > 0 and len(dupes) > 0:
                status = "gaps_and_duplicates"
            elif total_missing > 0:
                status = "has_gaps"
            elif len(dupes) > 0:
                status = "has_duplicates"

            results.append({
                "symbol": sym,
                "timeframe": tf,
                "total_candles": len(timestamps),
                "first_ms": timestamps[0],
                "last_ms": timestamps[-1],
                "expected_candles": int((timestamps[-1] - timestamps[0]) / step_ms) + 1,
                "missing_count": total_missing,
                "duplicate_timestamps": len(dupes),
                "gaps": gaps[:50],  # limit to first 50 gaps
                "total_gaps": len(gaps),
                "status": status,
            })

    return {"results": results}


# ─── Batch Candle API ───

@app.get("/data/candles/batch")
async def candles_batch(
    symbols: str = "",
    timeframes: str = "",
    limit: int = 200,
):
    """Fetch candles for multiple symbols/timeframes in one request.

    Query params:
        symbols: comma-separated, e.g. "BTC/USDT,ETH/USDT"
        timeframes: comma-separated, e.g. "1h,4h"
        limit: candles per series (default 200)
    """
    if not db_session:
        raise HTTPException(503, "Database not connected")
    if not symbols or not timeframes:
        raise HTTPException(400, "symbols and timeframes are required")

    from crypto_mega.data.store import CandleStore
    store = CandleStore(db_session)
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    tf_list = [t.strip() for t in timeframes.split(",") if t.strip()]

    data = await store.fetch_multi(sym_list, tf_list, limit=limit)

    result = {}
    for key, df in data.items():
        result[key] = {
            "candles": len(df),
            "data": df.to_dict(orient="list"),
        }

    return {"series": result, "symbols": sym_list, "timeframes": tf_list}


# ─── Exploration System ───

@app.get("/explore/stats")
async def explore_stats():
    """Get exploration system statistics."""
    if _strategy_explorer is None:
        return {
            "running": False,
            "message": "Explorer not started. Set AUTO_START_EXPLORER=true or call POST /explore/start",
        }
    return await _strategy_explorer.get_stats()


@app.get("/explore/leaderboard")
async def explore_leaderboard(
    limit: int = 50,
    sort_by: str = "sharpe_ratio",
    min_trades: int = 5,
):
    """Get exploration results leaderboard."""
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from crypto_mega.engine.explorer import StrategyExplorer
    explorer = _strategy_explorer or StrategyExplorer(db_session, config.exploration)
    return {
        "leaderboard": await explorer.get_leaderboard(limit, sort_by, min_trades),
    }


@app.post("/explore/start")
async def explore_start():
    """Start the strategy explorer."""
    global _strategy_explorer, _explorer_task
    if _strategy_explorer and _strategy_explorer._running:
        return {"status": "already_running", "message": "Explorer is already running"}
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from crypto_mega.engine.explorer import StrategyExplorer
    _strategy_explorer = StrategyExplorer(db_session, config.exploration)
    _explorer_task = asyncio.create_task(_strategy_explorer.run_loop())
    return {"status": "started", "message": "Explorer started. Discovering symbols from exchanges..."}


@app.post("/explore/stop")
async def explore_stop():
    """Stop the strategy explorer."""
    if _strategy_explorer:
        _strategy_explorer.stop()
        return {"status": "stopped", "message": "Explorer stopped"}
    return {"status": "not_running", "message": "Explorer was not running"}


@app.post("/explore/generate")
async def explore_generate(count: int = 10):
    """Manually generate exploration tasks."""
    global _strategy_explorer
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from crypto_mega.engine.explorer import StrategyExplorer

    # Reuse existing explorer or create persistent one
    if _strategy_explorer is None:
        _strategy_explorer = StrategyExplorer(db_session, config.exploration)

    if not _strategy_explorer._available_symbols:
        await _strategy_explorer.refresh_symbols()

    if not _strategy_explorer._available_symbols:
        return {
            "generated": 0,
            "message": "No symbols discovered. Check exchange connectivity.",
            "exchanges_tried": config.exploration.exchanges,
        }

    generated = await _strategy_explorer.generate_batch(count)
    dispatched = await _strategy_explorer.dispatch_tasks()
    return {
        "generated": generated,
        "dispatched": dispatched,
        "message": f"Generated {generated} tasks, dispatched {dispatched} to workers",
    }


@app.get("/explore/promotions")
async def explore_promotions():
    """Get exploration results that qualify for promotion to paper trading."""
    if not db_session:
        raise HTTPException(503, "Database not connected")
    from crypto_mega.engine.explorer import StrategyExplorer
    explorer = _strategy_explorer or StrategyExplorer(db_session, config.exploration)
    promoted = await explorer.check_promotions()
    return {"promoted": promoted, "count": len(promoted)}


@app.get("/explore/symbols")
async def explore_symbols():
    """Get currently discovered symbols per exchange."""
    if _strategy_explorer:
        return {
            "symbols": {
                ex: syms for ex, syms in _strategy_explorer._available_symbols.items()
            },
        }
    return {"symbols": {}, "message": "Explorer not started"}


@app.post("/explore/refresh-symbols")
async def explore_refresh_symbols():
    """Manually refresh available symbols from exchanges."""
    global _strategy_explorer
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from crypto_mega.engine.explorer import StrategyExplorer
    if _strategy_explorer is None:
        _strategy_explorer = StrategyExplorer(db_session, config.exploration)

    await _strategy_explorer.refresh_symbols()
    symbols_info = {
        ex: len(syms)
        for ex, syms in _strategy_explorer._available_symbols.items()
    }
    total = sum(symbols_info.values())
    return {
        "symbols": symbols_info,
        "total": total,
        "message": f"Discovered {total} symbols from {len(symbols_info)} exchanges" if total > 0
                   else "No symbols found. Exchanges may be unreachable.",
    }


@app.get("/workers")
async def list_workers():
    """Get registered worker nodes."""
    if not db_session:
        raise HTTPException(503, "Database not connected")

    from sqlalchemy import select
    from crypto_mega.data.models import WorkerNodeRecord
    async with db_session() as session:
        result = await session.execute(
            select(WorkerNodeRecord).order_by(WorkerNodeRecord.last_heartbeat.desc())
        )
        workers = result.scalars().all()

    return {
        "workers": [
            {
                "id": w.id,
                "hostname": w.hostname,
                "ip": w.ip_address,
                "max_workers": w.max_workers,
                "current_tasks": w.current_tasks,
                "total_completed": w.total_completed,
                "status": w.status,
                "last_heartbeat": w.last_heartbeat.isoformat() if w.last_heartbeat else None,
            }
            for w in workers
        ],
        "online": sum(1 for w in workers if w.status == "online"),
        "total_capacity": sum(w.max_workers for w in workers if w.status == "online"),
    }


@app.get("/system/alerts")
async def system_alerts():
    """All system alerts."""
    return {"alerts": _system_alerts}


@app.get("/logs")
async def get_logs(limit: int = 200, since: float = 0.0):
    """Get recent log entries from ring buffer."""
    return {"logs": _log_buffer.get_recent(limit, since)}


@app.websocket("/ws/logs")
async def websocket_logs(ws: WebSocket):
    """Stream logs in real-time via WebSocket."""
    await ws.accept()
    last_ts = time.time()
    try:
        while True:
            entries = _log_buffer.get_recent(limit=50, since=last_ts)
            if entries:
                last_ts = entries[-1]["ts"]
                await ws.send_json({"type": "logs", "entries": entries})
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass


# ─── Web UI ───

@app.get("/ui", include_in_schema=False)
async def dashboard_ui():
    """Full web dashboard UI."""
    from fastapi.responses import HTMLResponse
    from crypto_mega.api.ui import DASHBOARD_HTML
    return HTMLResponse(
        content=DASHBOARD_HTML,
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


# ─── System endpoints ───

@app.get("/", include_in_schema=False)
async def root():
    """Landing page — system overview and quick start."""
    from fastapi.responses import HTMLResponse
    from string import Template

    registered = strategy_loader.list_all()
    running = signal_engine.get_status()
    risk_status = risk_manager.get_status()

    strat_items = ""
    if registered:
        for name in registered:
            strat_items += "<li><code>" + name + "</code></li>"
    else:
        strat_items = "<li><em>None loaded — POST /strategies/load-directory first</em></li>"

    running_rows = ""
    if running:
        for sid, info in running.items():
            sc = "#4CAF50" if info["status"] == "running" else "#ff9800"
            running_rows += (
                "<tr><td><code>" + sid[:8] + "...</code></td>"
                "<td>" + info["name"] + "</td>"
                '<td style="color:' + sc + '">' + info["status"] + "</td>"
                "<td>" + str(info["signals"]) + "</td>"
                "<td>" + str(info["priority"]) + "</td></tr>"
            )

    db_label = "connected" if db_session else "no db"
    db_class = "status" if db_session else "status warn"
    equity = f"${risk_status['equity']:,.2f}"
    drawdown = f"{risk_status['drawdown_pct']:.1f}%"
    ks_label = "ACTIVE" if risk_status["kill_switch"] else "off"
    ks_class = "status warn" if risk_status["kill_switch"] else "status"

    running_table = ""
    if running_rows:
        running_table = (
            '<div class="card"><h3>Running Strategies</h3>'
            "<table><tr><th>ID</th><th>Name</th><th>Status</th>"
            "<th>Signals</th><th>Priority</th></tr>"
            + running_rows + "</table></div>"
        )

    html = Template("""<!DOCTYPE html>
<html>
<head>
    <title>CryptoMega</title>
    <meta charset="utf-8">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'SF Mono', 'Fira Code', monospace; background: #0a0a0a; color: #e0e0e0; padding: 40px; max-width: 1000px; margin: 0 auto; }
        h1 { color: #00ff88; font-size: 28px; margin-bottom: 5px; }
        h2 { color: #888; font-size: 14px; font-weight: normal; margin-bottom: 30px; }
        h3 { color: #00bfff; margin: 25px 0 10px; font-size: 16px; }
        .card { background: #151515; border: 1px solid #2a2a2a; border-radius: 8px; padding: 20px; margin: 15px 0; }
        .status { display: inline-block; background: #1a3a1a; color: #4CAF50; padding: 3px 10px; border-radius: 4px; font-size: 13px; }
        .status.warn { background: #3a2a1a; color: #ff9800; }
        a { color: #00bfff; text-decoration: none; }
        a:hover { text-decoration: underline; }
        code { background: #1a1a2e; padding: 2px 6px; border-radius: 3px; color: #ff6b9d; font-size: 13px; }
        pre { background: #111; border: 1px solid #333; border-radius: 6px; padding: 15px; overflow-x: auto; font-size: 13px; line-height: 1.5; margin: 10px 0; }
        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; color: #888; padding: 8px; border-bottom: 1px solid #333; }
        td { padding: 8px; border-bottom: 1px solid #1a1a1a; }
        ul { padding-left: 20px; line-height: 1.8; }
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }
        @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
        .ep { margin: 4px 0; }
        .m { display: inline-block; width: 55px; font-weight: bold; font-size: 11px; }
        .g { color: #4CAF50; } .p { color: #ff9800; }
    </style>
</head>
<body>
    <h1>CryptoMega</h1>
    <h2>Massive crypto trading signal system</h2>

    <div class="grid">
        <div class="card">
            <h3>System</h3>
            <p>DB: <span class="$db_class">$db_label</span></p>
            <p style="margin-top:8px">Strategies loaded: <strong>$n_registered</strong></p>
            <p>Running: <strong>$n_running</strong></p>
            <p>WebSocket clients: <strong>$n_ws</strong></p>
        </div>
        <div class="card">
            <h3>Risk</h3>
            <p>Equity: <strong>$equity</strong></p>
            <p>Drawdown: <strong>$drawdown</strong></p>
            <p>Open positions: <strong>$n_positions</strong></p>
            <p>Kill switch: <span class="$ks_class">$ks_label</span></p>
        </div>
    </div>

    <div class="card">
        <h3>Available Strategies</h3>
        <ul>$strat_items</ul>
    </div>

    $running_table

    <div class="card" style="border-color: #00ff88; border-width: 2px;">
        <h3 style="color: #00ff88;">Dashboard</h3>
        <p style="margin-bottom: 15px;">Full web UI with leaderboard, signals, positions, and controls:</p>
        <a href="/ui" style="display: inline-block; background: #00ff88; color: #0a0a0a; padding: 10px 30px; border-radius: 6px; font-weight: bold; text-decoration: none;">Open Dashboard &rarr;</a>
    </div>

    <div class="card">
        <h3>Quick Start (CLI)</h3>
        <p>Or use the API directly:</p>
        <pre>curl -X POST /engine/start?symbols=BTC/USDT,ETH/USDT&amp;exchange=binance</pre>
        <p>Load custom strategy from code:</p>
        <pre>curl -X POST /strategies/load-code -H "Content-Type: application/json" \
  -d '{"name": "my_strat", "symbols": ["BTC/USDT"],
       "code": "class MyStrat(BaseStrategy):\n  def generate_signals(self, data):\n    return []"}'</pre>
        <p><a href="/docs">Swagger docs &rarr;</a></p>
    </div>

    <div class="card">
        <h3>API Endpoints</h3>
        <div class="ep"><span class="m g">GET</span> <a href="/docs">/docs</a> &mdash; Interactive API docs (Swagger UI)</div>
        <div class="ep"><span class="m g">GET</span> <a href="/health">/health</a> &mdash; Health check</div>
        <div class="ep"><span class="m g">GET</span> <a href="/status">/status</a> &mdash; Full system status</div>
        <div class="ep"><span class="m g">GET</span> <a href="/strategies">/strategies</a> &mdash; List strategies</div>
        <div class="ep"><span class="m p">POST</span> /strategies/load-code &mdash; Load strategy from code</div>
        <div class="ep"><span class="m p">POST</span> /strategies/load-directory &mdash; Load from file directory</div>
        <div class="ep"><span class="m p">POST</span> /backtest &mdash; Run backtest / grid search</div>
        <div class="ep"><span class="m g">GET</span> <a href="/resources">/resources</a> &mdash; Resource allocation</div>
        <div class="ep"><span class="m p">POST</span> /resources/priority &mdash; Set strategy priority</div>
        <div class="ep"><span class="m g">GET</span> <a href="/execution/pending">/execution/pending</a> &mdash; Pending signals</div>
        <div class="ep"><span class="m p">POST</span> /execution/approve &mdash; Approve trade execution</div>
        <div class="ep"><span class="m g">GET</span> <a href="/monitor/stats">/monitor/stats</a> &mdash; Performance + recommendations</div>
        <div class="ep"><span class="m g">GET</span> <a href="/monitor/alerts">/monitor/alerts</a> &mdash; Divergence alerts</div>
        <div class="ep"><span class="m g">GET</span> <a href="/risk">/risk</a> &mdash; Risk / portfolio status</div>
        <div class="ep"><span class="m p">POST</span> /risk/kill-switch/activate &mdash; Emergency stop</div>
        <div class="ep"><span class="m p">POST</span> /risk/kill-switch/deactivate &mdash; Resume trading</div>
        <br>
        <div class="ep"><strong>WebSocket:</strong></div>
        <div class="ep"><code>/ws/signals</code> &mdash; Real-time signal stream</div>
        <div class="ep"><code>/ws/monitor</code> &mdash; Live stats push (every 5s)</div>
    </div>

    <div class="card" style="border-color: #333; color: #666; font-size: 12px;">
        CryptoMega v0.1.0 | <a href="/docs">Swagger</a> | <a href="/redoc">ReDoc</a>
    </div>
</body>
</html>""").safe_substitute(
        db_class=db_class,
        db_label=db_label,
        n_registered=len(registered),
        n_running=len(running),
        n_ws=len(ws_manager.active),
        equity=equity,
        drawdown=drawdown,
        n_positions=risk_status["positions"],
        ks_class=ks_class,
        ks_label=ks_label,
        strat_items=strat_items,
        running_table=running_table,
    )
    return HTMLResponse(content=html)


@app.get("/health")
async def health():
    engine_running = _engine_task is not None and not _engine_task.done()
    exchange_id = data_provider._exchange_id or "none"
    uptime = time.time() - _app_start_time

    # Data staleness check — relative to the smallest active timeframe
    data_status = "ok"
    data_age_sec = 0.0
    min_tf_seconds = 3600  # default assume 1h
    if data_provider._cache:
        newest = 0
        for key, df in data_provider._cache.items():
            if len(df) == 0:
                continue
            ts = df.iloc[-1]["timestamp"].timestamp()
            if ts > newest:
                newest = ts
            # Extract timeframe to get the right staleness threshold
            parts = key.split("_")
            tf = parts[-1] if len(parts) > 1 else "1h"
            try:
                tf_sec = data_provider._timeframe_to_delta(tf).total_seconds()
                min_tf_seconds = min(min_tf_seconds, tf_sec)
            except Exception:
                pass
        data_age_sec = time.time() - newest if newest > 0 else 0
        # Stale if data is older than 1.5x the timeframe
        if data_age_sec > min_tf_seconds * 3:
            data_status = "critical"
        elif data_age_sec > min_tf_seconds * 2:
            data_status = "stale"
    else:
        data_status = "no_data"

    # Recent errors count
    recent_errors = sum(
        1 for a in _system_alerts
        if a["level"] == "error" and time.time() - a["ts"] < 300
    )

    return {
        "status": "ok" if engine_running else "idle",
        "uptime_sec": round(uptime),
        "db": "connected" if db_session else "unavailable",
        "exchange": exchange_id,
        "engine_running": engine_running,
        "strategies_loaded": len(strategy_loader.list_all()),
        "strategies_running": len(signal_engine._instances),
        "ws_clients": len(ws_manager.active),
        "data_status": data_status,
        "data_age_sec": round(data_age_sec),
        "recent_errors": recent_errors,
        "alerts": _system_alerts[-10:],
    }


@app.get("/status")
async def system_status():
    return {
        "engine": signal_engine.get_status(),
        "resources": resource_manager.get_status(),
        "risk": risk_manager.get_status(),
        "monitor": monitor.get_all_stats(),
        "ws_clients": len(ws_manager.active),
    }
