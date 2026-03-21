"""Signal Engine — orchestrates strategy execution and signal generation."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from crypto_mega.data.provider import DataProvider
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, StrategyConfig, StrategyStatus

logger = logging.getLogger(__name__)


@dataclass
class StrategyInstance:
    """A running strategy with its state."""
    strategy: BaseStrategy
    config: StrategyConfig
    status: StrategyStatus = StrategyStatus.PENDING
    signals_generated: int = 0
    last_run: float = 0.0
    errors: list[str] = field(default_factory=list)
    cumulative_pnl: float = 0.0


class SignalEngine:
    """
    Core engine that runs strategies, collects signals, and dispatches them.

    This is the beating heart of the system:
    - Runs multiple strategies in parallel
    - Feeds them market data
    - Collects and routes signals
    - Respects resource allocation priorities
    """

    def __init__(self, data_provider: DataProvider):
        self.data_provider = data_provider
        self._instances: dict[str, StrategyInstance] = {}
        self._signal_handlers: list[callable] = []
        self._running = False

    def add_strategy(self, strategy: BaseStrategy, config: StrategyConfig) -> str:
        """Register a strategy for execution."""
        instance = StrategyInstance(strategy=strategy, config=config)
        self._instances[config.id] = instance
        logger.info(f"Added strategy: {strategy.name} [{config.id[:8]}]")
        return config.id

    def remove_strategy(self, strategy_id: str) -> None:
        """Remove a strategy from execution."""
        if strategy_id in self._instances:
            self._instances[strategy_id].status = StrategyStatus.STOPPED
            del self._instances[strategy_id]
            logger.info(f"Removed strategy: {strategy_id[:8]}")

    def pause_strategy(self, strategy_id: str) -> None:
        if strategy_id in self._instances:
            self._instances[strategy_id].status = StrategyStatus.PAUSED

    def resume_strategy(self, strategy_id: str) -> None:
        if strategy_id in self._instances:
            self._instances[strategy_id].status = StrategyStatus.RUNNING

    def on_signal(self, handler: callable) -> None:
        """Register a signal handler (e.g., execution engine, monitor, logger)."""
        self._signal_handlers.append(handler)

    async def run_once(self, strategy_id: str) -> list[Signal]:
        """Run a single strategy once and return signals."""
        instance = self._instances.get(strategy_id)
        if not instance:
            return []

        config = instance.config
        try:
            # Fetch required data
            timeframe_strs = [tf.value for tf in config.timeframes]
            data = await self.data_provider.fetch_multi(
                config.symbols, timeframe_strs, limit=instance.strategy.required_history()
            )

            # Generate signals
            logger.info(
                f"Running strategy: {config.name} | "
                f"symbols={config.symbols} | data_keys={list(data.keys())}"
            )
            signals = instance.strategy.generate_signals(data)

            # Tag signals with strategy info
            for sig in signals:
                sig.strategy_id = config.id

            instance.signals_generated += len(signals)
            instance.last_run = time.time()
            instance.status = StrategyStatus.RUNNING

            # Log signal details
            for sig in signals:
                logger.info(
                    f"Signal: {config.name} -> {sig.direction.value.upper()} "
                    f"{sig.symbol} @ {sig.price:.2f} "
                    f"(strength={sig.strength:.2f}"
                    f"{f', SL={sig.stop_loss:.2f}' if sig.stop_loss else ''}"
                    f"{f', TP={sig.take_profit:.2f}' if sig.take_profit else ''}"
                    f")"
                )

            if not signals:
                logger.debug(f"Strategy {config.name}: no signals this cycle")

            # Dispatch to handlers
            for handler in self._signal_handlers:
                for sig in signals:
                    try:
                        await handler(sig)
                    except Exception as e:
                        logger.error(f"Signal handler error: {e}")

            return signals

        except Exception as e:
            instance.errors.append(str(e))
            instance.status = StrategyStatus.ERROR
            logger.error(f"Strategy {config.name} error: {e}")
            return []

    async def run_loop(self, interval_seconds: float = 60.0):
        """Main loop — continuously runs all active strategies. Resilient to errors."""
        self._running = True
        logger.info(f"Signal engine started with {len(self._instances)} strategies")

        cycle = 0
        consecutive_errors = 0
        while self._running:
            cycle += 1
            try:
                # Sort by priority — higher priority runs first / gets more cycles
                active = [
                    inst for inst in self._instances.values()
                    if inst.status in (StrategyStatus.PENDING, StrategyStatus.RUNNING)
                ]
                active.sort(key=lambda x: x.config.priority, reverse=True)

                logger.info(
                    f"=== Cycle #{cycle} === "
                    f"{len(active)} strategies | "
                    f"next in {interval_seconds}s"
                )
                t0 = time.time()
                tasks = [self.run_once(inst.config.id) for inst in active]
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    total_signals = sum(
                        len(r) for r in results if isinstance(r, list)
                    )
                    errors = sum(
                        1 for r in results if isinstance(r, Exception)
                    )
                    elapsed = time.time() - t0
                    logger.info(
                        f"Cycle #{cycle} done in {elapsed:.2f}s | "
                        f"{total_signals} signals | "
                        f"{errors} errors"
                    )
                    consecutive_errors = 0

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                consecutive_errors += 1
                logger.error(f"Cycle #{cycle} error (#{consecutive_errors}): {e}")
                if consecutive_errors > 10:
                    logger.critical(f"Too many consecutive errors, stopping engine")
                    self._running = False
                    break
                # Backoff before retry
                await asyncio.sleep(min(interval_seconds * (consecutive_errors // 5 + 1), 300))

    def stop(self):
        self._running = False
        logger.info("Signal engine stopped")

    def get_status(self) -> dict[str, dict]:
        """Get status of all strategies."""
        return {
            sid: {
                "name": inst.strategy.name,
                "status": inst.status.value,
                "signals": inst.signals_generated,
                "last_run": inst.last_run,
                "priority": inst.config.priority,
                "errors": inst.errors[-5:],  # last 5 errors
            }
            for sid, inst in self._instances.items()
        }
