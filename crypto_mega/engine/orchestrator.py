"""Orchestrator — ties all components together and manages the main loop."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from crypto_mega.config.settings import SystemConfig
from crypto_mega.data.provider import DataProvider
from crypto_mega.engine.signal_engine import SignalEngine
from crypto_mega.execution.executor import ExecutionEngine, ExchangeConnection
from crypto_mega.monitor.monitor import PerformanceMonitor
from crypto_mega.resource_manager.manager import ResourceManager
from crypto_mega.risk.risk_manager import RiskManager
from crypto_mega.strategies.loader import strategy_loader
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig, TimeFrame

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Master orchestrator that wires everything together.

    Flow:
    1. Load strategies from directory/code
    2. For each strategy, fetch data and generate signals
    3. Signals pass through RiskManager for position sizing
    4. Approved signals go to ExecutionEngine
    5. Monitor tracks theoretical vs real performance
    6. ResourceManager adjusts priorities based on performance
    """

    def __init__(
        self,
        config: SystemConfig | None = None,
        strategy_dir: str = "strategies_user",
        symbols: list[str] | None = None,
    ):
        self.config = config or SystemConfig()
        self.symbols = symbols or ["BTC/USDT", "ETH/USDT"]

        # Initialize components
        self.data_provider = DataProvider()
        self.signal_engine = SignalEngine(self.data_provider)
        self.execution_engine = ExecutionEngine()
        self.resource_manager = ResourceManager(
            total_workers=self.config.resources.max_workers,
            mode="hybrid",
        )
        self.monitor = PerformanceMonitor()
        self.risk_manager = RiskManager(self.config.risk)

        # Wire up signal pipeline
        self.signal_engine.on_signal(self._process_signal)

        # Load strategies
        self._strategy_dir = strategy_dir
        self._load_strategies()

    def _load_strategies(self):
        """Load all strategies from the configured directory."""
        classes = strategy_loader.load_directory(self._strategy_dir)
        logger.info(f"Loaded {len(classes)} strategy classes")

        for cls in classes:
            cfg = StrategyConfig(
                name=cls.__name__,
                symbols=self.symbols,
                timeframes=[TimeFrame.H1],
            )
            instance = cls(cfg)
            sid = self.signal_engine.add_strategy(instance, cfg)
            self.resource_manager.set_allocation(sid, cfg.priority)

    async def _process_signal(self, signal: Signal) -> None:
        """Pipeline: Signal -> Risk Check -> Execute/Queue."""
        if signal.direction == SignalDirection.HOLD:
            return

        # Risk check
        allowed, reason, quantity = self.risk_manager.check_signal(signal)
        if not allowed:
            logger.info(f"Signal blocked by risk manager: {reason}")
            return

        signal.metadata["quantity"] = quantity

        # Forward to execution
        await self.execution_engine.handle_signal(signal)

    async def start(self, interval: float = 60.0):
        """Start the main loop."""
        # Init exchange connection
        await self.data_provider.init_exchange("binance", {"enableRateLimit": True})

        logger.info(f"Orchestrator starting — {len(self.signal_engine._instances)} strategies, interval={interval}s")
        logger.info(f"Symbols: {self.symbols}")

        # Handle graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))

        try:
            await self.signal_engine.run_loop(interval)
        except asyncio.CancelledError:
            pass
        finally:
            await self.cleanup()

    async def stop(self):
        """Graceful shutdown."""
        logger.info("Orchestrator stopping...")
        self.signal_engine.stop()

    async def cleanup(self):
        """Cleanup resources."""
        await self.data_provider.close()
        await self.execution_engine.close_all()
        logger.info("Orchestrator shutdown complete")
