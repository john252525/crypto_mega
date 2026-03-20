"""FastAPI application — REST API + WebSocket for the entire system."""

from __future__ import annotations

import asyncio
import json
import logging
import os
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

from crypto_mega.backtester.backtester import Backtester
from crypto_mega.config.settings import RiskConfig, SystemConfig
from crypto_mega.data.provider import DataProvider
from crypto_mega.engine.signal_engine import SignalEngine
from crypto_mega.execution.executor import ExecutionEngine
from crypto_mega.monitor.monitor import PerformanceMonitor
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
backtester = Backtester()
db_session = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown lifecycle. Graceful — never crashes on missing deps."""
    global db_session

    # Init database (optional — works without it)
    try:
        from crypto_mega.data.models import init_db
        db_session = await init_db(config.db.url)
        logger.info(f"Database initialized: {config.db.url[:30]}...")
    except Exception as e:
        logger.warning(f"Database not available, running without persistence: {e}")
        db_session = None

    # Load strategies from directory
    try:
        strategy_loader.load_directory(config.strategies_dir)
        logger.info(f"Loaded strategies from {config.strategies_dir}")
    except Exception as e:
        logger.warning(f"Could not load strategies: {e}")

    yield

    # Cleanup
    try:
        await data_provider.close()
    except Exception:
        pass
    try:
        await execution_engine.close_all()
    except Exception:
        pass
    logger.info("App shutdown complete")


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
    """List all registered strategies."""
    return {
        "registered": {name: str(cls) for name, cls in strategy_loader.list_all().items()},
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

    <div class="card">
        <h3>Quick Start</h3>
        <p>1. Load example strategies:</p>
        <pre>curl -X POST /strategies/load-directory?directory=strategies_user</pre>
        <p>2. Run backtest:</p>
        <pre>curl -X POST /backtest -H "Content-Type: application/json" \
  -d '{"strategy_name": "SMACrossover", "symbols": ["BTC/USDT"]}'</pre>
        <p>3. Grid search (find best parameters):</p>
        <pre>curl -X POST /backtest -H "Content-Type: application/json" \
  -d '{"strategy_name": "SMACrossover", "symbols": ["BTC/USDT"],
       "param_grid": {"fast_period": [5,10,15], "slow_period": [30,50,100]}}'</pre>
        <p>4. Load custom strategy from code:</p>
        <pre>curl -X POST /strategies/load-code -H "Content-Type: application/json" \
  -d '{"name": "my_strat", "symbols": ["BTC/USDT"],
       "code": "class MyStrat(BaseStrategy):\n  def generate_signals(self, data):\n    return []"}'</pre>
        <p>Or just use <a href="/docs">interactive Swagger docs &rarr;</a></p>
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
    return {
        "status": "ok",
        "db": "connected" if db_session else "unavailable",
        "strategies": len(signal_engine._instances),
        "ws_clients": len(ws_manager.active),
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
