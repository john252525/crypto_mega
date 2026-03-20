"""Backtester — runs strategies on historical data with full parameter grid search."""

from __future__ import annotations

import itertools
import logging
import time
from copy import deepcopy
from dataclasses import dataclass, field

import pandas as pd

from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig, StrategyStats

logger = logging.getLogger(__name__)


@dataclass
class BacktestTrade:
    symbol: str = ""
    direction: SignalDirection = SignalDirection.LONG
    entry_price: float = 0.0
    exit_price: float = 0.0
    entry_time: str = ""
    exit_time: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0


@dataclass
class BacktestResult:
    strategy_name: str = ""
    parameters: dict = field(default_factory=dict)
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_trade_pnl: float = 0.0
    trades: list[BacktestTrade] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)
    run_time_sec: float = 0.0


class Backtester:
    """
    Historical backtesting engine.

    Supports:
    - Single run with fixed params
    - Grid search over parameter space
    - Random search (sample N combos from param grid)
    - Walk-forward optimization
    """

    def __init__(self, initial_capital: float = 10000.0, commission_pct: float = 0.1):
        self.initial_capital = initial_capital
        self.commission_pct = commission_pct

    def run(
        self,
        strategy: BaseStrategy,
        data: dict[str, pd.DataFrame],
        config: StrategyConfig,
    ) -> BacktestResult:
        """Run backtest with current strategy parameters."""
        start = time.time()
        signals = strategy.generate_signals(data)

        trades = self._simulate_trades(signals, data)
        result = self._compute_stats(trades, strategy.name, config.parameters)
        result.run_time_sec = time.time() - start
        return result

    def grid_search(
        self,
        strategy_cls: type,
        data: dict[str, pd.DataFrame],
        base_config: StrategyConfig,
        param_grid: dict[str, list] | None = None,
        max_combinations: int | None = None,
    ) -> list[BacktestResult]:
        """
        Run backtest for every parameter combination.
        Returns results sorted by total_pnl descending.
        """
        strategy_instance = strategy_cls(base_config)
        grid = param_grid or strategy_instance.param_grid()

        if not grid:
            return [self.run(strategy_instance, data, base_config)]

        keys = list(grid.keys())
        values = list(grid.values())
        combos = list(itertools.product(*values))

        if max_combinations and len(combos) > max_combinations:
            import random
            combos = random.sample(combos, max_combinations)

        results = []
        total = len(combos)
        logger.info(f"Grid search: {total} combinations for {strategy_cls.__name__}")

        for i, combo in enumerate(combos):
            params = dict(zip(keys, combo))
            cfg = deepcopy(base_config)
            cfg.parameters = params

            strat = strategy_cls(cfg)
            result = self.run(strat, data, cfg)
            results.append(result)

            if (i + 1) % 100 == 0:
                logger.info(f"Grid search progress: {i + 1}/{total}")

        results.sort(key=lambda r: r.total_pnl, reverse=True)
        return results

    def _simulate_trades(self, signals: list[Signal], data: dict[str, pd.DataFrame]) -> list[BacktestTrade]:
        """Simulate trades from signals using simple fill model."""
        trades = []
        open_positions: dict[str, Signal] = {}

        for signal in sorted(signals, key=lambda s: s.timestamp):
            symbol = signal.symbol

            if signal.direction in (SignalDirection.LONG, SignalDirection.SHORT):
                # Close existing position in opposite direction
                if symbol in open_positions:
                    prev = open_positions.pop(symbol)
                    trade = self._close_trade(prev, signal)
                    trades.append(trade)
                open_positions[symbol] = signal

            elif signal.direction == SignalDirection.CLOSE and symbol in open_positions:
                prev = open_positions.pop(symbol)
                trade = self._close_trade(prev, signal)
                trades.append(trade)

        return trades

    def _close_trade(self, entry_signal: Signal, exit_signal: Signal) -> BacktestTrade:
        """Create a closed trade record."""
        if entry_signal.direction == SignalDirection.LONG:
            pnl_pct = (exit_signal.price - entry_signal.price) / entry_signal.price * 100
        else:  # SHORT
            pnl_pct = (entry_signal.price - exit_signal.price) / entry_signal.price * 100

        pnl_pct -= self.commission_pct * 2  # entry + exit commission

        return BacktestTrade(
            symbol=entry_signal.symbol,
            direction=entry_signal.direction,
            entry_price=entry_signal.price,
            exit_price=exit_signal.price,
            entry_time=str(entry_signal.timestamp),
            exit_time=str(exit_signal.timestamp),
            pnl=self.initial_capital * (pnl_pct / 100),
            pnl_pct=pnl_pct,
        )

    def _compute_stats(self, trades: list[BacktestTrade], name: str, params: dict) -> BacktestResult:
        """Compute aggregate statistics from trade list."""
        if not trades:
            return BacktestResult(strategy_name=name, parameters=params)

        winning = [t for t in trades if t.pnl > 0]
        losing = [t for t in trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades)
        gross_profit = sum(t.pnl for t in winning) if winning else 0
        gross_loss = abs(sum(t.pnl for t in losing)) if losing else 1

        # Equity curve and max drawdown
        equity = [self.initial_capital]
        for t in trades:
            equity.append(equity[-1] + t.pnl)

        peak = equity[0]
        max_dd = 0.0
        for val in equity:
            if val > peak:
                peak = val
            dd = (peak - val) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd

        # Sharpe ratio (simplified — daily-ish returns)
        if len(trades) > 1:
            returns = [t.pnl_pct for t in trades]
            import numpy as np
            avg_ret = np.mean(returns)
            std_ret = np.std(returns)
            sharpe = (avg_ret / std_ret * (252 ** 0.5)) if std_ret > 0 else 0.0
        else:
            sharpe = 0.0

        return BacktestResult(
            strategy_name=name,
            parameters=params,
            total_trades=len(trades),
            winning_trades=len(winning),
            losing_trades=len(losing),
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl / self.initial_capital * 100,
            max_drawdown=max_dd,
            sharpe_ratio=sharpe,
            win_rate=len(winning) / len(trades) * 100 if trades else 0,
            profit_factor=gross_profit / gross_loss if gross_loss > 0 else float("inf"),
            avg_trade_pnl=total_pnl / len(trades),
            trades=trades,
            equity_curve=equity,
        )
