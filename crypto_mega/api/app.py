"""FastAPI application — REST API for the entire system."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from crypto_mega.backtester.backtester import Backtester
from crypto_mega.config.settings import RiskConfig, SystemConfig
from crypto_mega.data.provider import DataProvider
from crypto_mega.engine.signal_engine import SignalEngine
from crypto_mega.execution.executor import ExecutionEngine
from crypto_mega.monitor.monitor import PerformanceMonitor
from crypto_mega.resource_manager.manager import ResourceManager
from crypto_mega.risk.risk_manager import RiskManager
from crypto_mega.strategies.loader import strategy_loader
from crypto_mega.utils.types import StrategyConfig, TimeFrame

logger = logging.getLogger(__name__)

app = FastAPI(title="CryptoMega", version="0.1.0", description="Massive crypto trading signal system")

# ─── Global state (initialized on startup) ───
config = SystemConfig()
data_provider = DataProvider()
signal_engine = SignalEngine(data_provider)
execution_engine = ExecutionEngine()
resource_manager = ResourceManager(total_workers=config.resources.max_workers, mode="hybrid")
monitor = PerformanceMonitor()
risk_manager = RiskManager(config.risk)
backtester = Backtester()


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


class ExecuteSignalRequest(BaseModel):
    signal_index: int
    exchange_id: str | None = None


class ApproveAdjustmentRequest(BaseModel):
    index: int


# ─── Strategy endpoints ───

@app.post("/strategies/load-code")
async def load_strategy_from_code(req: StrategyCodeRequest):
    """Load a strategy from code string (the Vasya/GPT interface)."""
    classes = strategy_loader.load_from_code(req.code, req.name)
    if not classes:
        raise HTTPException(400, "No valid strategy classes found in code")

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
    """Run backtest for a strategy."""
    cls = strategy_loader.get(req.strategy_name)
    if not cls:
        raise HTTPException(404, f"Strategy not found: {req.strategy_name}")

    cfg = StrategyConfig(
        name=req.strategy_name,
        symbols=req.symbols,
        timeframes=[TimeFrame(tf) for tf in req.timeframes],
        parameters=req.parameters,
    )

    # Fetch historical data
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
    return {"status": "KILL SWITCH ACTIVATED"}


@app.post("/risk/kill-switch/deactivate")
async def deactivate_kill_switch():
    risk_manager.deactivate_kill_switch()
    return {"status": "kill switch deactivated"}


# ─── System endpoints ───

@app.get("/health")
async def health():
    return {"status": "ok", "strategies": len(signal_engine._instances)}


@app.get("/status")
async def system_status():
    return {
        "engine": signal_engine.get_status(),
        "resources": resource_manager.get_status(),
        "risk": risk_manager.get_status(),
        "monitor": monitor.get_all_stats(),
    }
