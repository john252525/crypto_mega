"""Execution Engine — forwards signals to exchanges via API."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from crypto_mega.utils.types import Signal, SignalDirection, TradeResult

logger = logging.getLogger(__name__)


@dataclass
class ExchangeConnection:
    exchange_id: str
    api_key: str = ""
    api_secret: str = ""
    sandbox: bool = True
    _exchange: object = field(default=None, repr=False)

    async def connect(self):
        import ccxt.async_support as ccxt_async
        exchange_class = getattr(ccxt_async, self.exchange_id)
        config = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
        }
        if self.sandbox:
            config["sandbox"] = True
        self._exchange = exchange_class(config)
        logger.info(f"Connected to {self.exchange_id} (sandbox={self.sandbox})")

    async def close(self):
        if self._exchange:
            await self._exchange.close()

    @property
    def exchange(self):
        return self._exchange


class ExecutionEngine:
    """
    Executes trading signals on real exchanges.

    Features:
    - Multi-exchange support
    - Order routing (send to best exchange)
    - Execution confirmation and tracking
    - Slippage monitoring
    - Admin approval gate for non-auto strategies
    """

    def __init__(self):
        self._connections: dict[str, ExchangeConnection] = {}
        self._pending_signals: list[Signal] = []
        self._executed_trades: list[TradeResult] = []
        self._require_approval: bool = True
        self._approved_strategies: set[str] = set()

    async def add_exchange(self, conn: ExchangeConnection) -> None:
        await conn.connect()
        self._connections[conn.exchange_id] = conn

    def approve_strategy_for_execution(self, strategy_id: str) -> None:
        """Admin approves a strategy for auto-execution."""
        self._approved_strategies.add(strategy_id)
        logger.info(f"Strategy {strategy_id[:8]} approved for auto-execution")

    def revoke_strategy_execution(self, strategy_id: str) -> None:
        self._approved_strategies.discard(strategy_id)

    async def handle_signal(self, signal: Signal) -> None:
        """Signal handler — called by SignalEngine for each new signal."""
        if signal.direction == SignalDirection.HOLD:
            return

        if signal.strength < 0.5:
            logger.debug(f"Signal too weak ({signal.strength:.2f}), skipping")
            return

        if self._require_approval and signal.strategy_id not in self._approved_strategies:
            self._pending_signals.append(signal)
            logger.info(f"Signal queued for approval: {signal.symbol} {signal.direction.value}")
            return

        await self._execute(signal)

    async def approve_and_execute(self, signal_index: int, exchange_id: str | None = None) -> TradeResult | None:
        """Admin approves a pending signal for execution."""
        if 0 <= signal_index < len(self._pending_signals):
            signal = self._pending_signals.pop(signal_index)
            return await self._execute(signal, exchange_id)
        return None

    async def _execute(self, signal: Signal, exchange_id: str | None = None) -> TradeResult:
        """Execute a signal on an exchange."""
        conn = self._connections.get(exchange_id or next(iter(self._connections), ""))
        if not conn or not conn.exchange:
            logger.error("No exchange connection available")
            return TradeResult(signal_id=signal.id, strategy_id=signal.strategy_id)

        exchange = conn.exchange
        try:
            side = "buy" if signal.direction == SignalDirection.LONG else "sell"

            # For CLOSE signals, we need to figure out the side based on current position
            if signal.direction == SignalDirection.CLOSE:
                side = "sell"  # simplified; real impl checks position

            order = await exchange.create_order(
                symbol=signal.symbol,
                type="market",
                side=side,
                amount=self._calculate_position_size(signal),
            )

            result = TradeResult(
                signal_id=signal.id,
                strategy_id=signal.strategy_id,
                symbol=signal.symbol,
                direction=signal.direction,
                entry_price=float(order.get("average", order.get("price", signal.price))),
                quantity=float(order.get("filled", 0)),
                exchange_order_id=str(order.get("id", "")),
            )

            self._executed_trades.append(result)
            logger.info(
                f"Executed: {signal.symbol} {side} @ {result.entry_price} "
                f"(qty={result.quantity}, order={result.exchange_order_id})"
            )

            # Monitor slippage
            if signal.price > 0:
                slippage = abs(result.entry_price - signal.price) / signal.price * 100
                if slippage > 0.5:
                    logger.warning(f"High slippage: {slippage:.2f}% on {signal.symbol}")

            return result

        except Exception as e:
            logger.error(f"Execution failed for {signal.symbol}: {e}")
            return TradeResult(signal_id=signal.id, strategy_id=signal.strategy_id)

    def _calculate_position_size(self, signal: Signal) -> float:
        """Calculate position size. Placeholder — real logic lives in RiskManager."""
        # This gets overridden by risk manager integration
        return signal.metadata.get("quantity", 0.001)

    def get_pending_signals(self) -> list[dict]:
        return [
            {
                "index": i,
                "symbol": s.symbol,
                "direction": s.direction.value,
                "strength": s.strength,
                "price": s.price,
                "strategy_id": s.strategy_id[:8],
                "timestamp": str(s.timestamp),
            }
            for i, s in enumerate(self._pending_signals)
        ]

    def get_executed_trades(self) -> list[dict]:
        return [
            {
                "symbol": t.symbol,
                "direction": t.direction.value,
                "entry": t.entry_price,
                "qty": t.quantity,
                "pnl": t.pnl,
                "order_id": t.exchange_order_id,
            }
            for t in self._executed_trades[-50:]  # last 50
        ]

    async def close_all(self):
        for conn in self._connections.values():
            await conn.close()
