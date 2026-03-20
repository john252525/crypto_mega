"""Tests for core components."""

import pandas as pd
import numpy as np
import pytest

from crypto_mega.backtester.backtester import Backtester
from crypto_mega.config.settings import RiskConfig
from crypto_mega.resource_manager.manager import ResourceManager
from crypto_mega.risk.risk_manager import RiskManager
from crypto_mega.strategies.base import BaseStrategy
from crypto_mega.strategies.loader import StrategyLoader
from crypto_mega.utils.types import Signal, SignalDirection, StrategyConfig, TimeFrame


# ─── Helpers ───

def make_ohlcv(n: int = 200, base_price: float = 100.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    np.random.seed(42)
    prices = base_price + np.cumsum(np.random.randn(n) * 0.5)
    prices = np.maximum(prices, 1.0)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
        "open": prices,
        "high": prices * (1 + np.random.rand(n) * 0.01),
        "low": prices * (1 - np.random.rand(n) * 0.01),
        "close": prices + np.random.randn(n) * 0.2,
        "volume": np.random.rand(n) * 1000 + 100,
    })


# ─── Strategy Loader Tests ───

class TestStrategyLoader:
    def test_load_from_code(self):
        loader = StrategyLoader()
        code = '''
class TestStrat(BaseStrategy):
    def generate_signals(self, data):
        return []
'''
        classes = loader.load_from_code(code, "test_code")
        assert len(classes) == 1
        assert classes[0].__name__ == "TestStrat"

    def test_load_from_code_with_signals(self):
        loader = StrategyLoader()
        code = '''
from crypto_mega.utils.types import Signal, SignalDirection

class SignalStrat(BaseStrategy):
    def generate_signals(self, data):
        return [Signal(symbol="BTC/USDT", direction=SignalDirection.LONG, price=50000)]
'''
        classes = loader.load_from_code(code, "signal_test")
        assert len(classes) == 1

        cfg = StrategyConfig(name="test")
        instance = classes[0](cfg)
        signals = instance.generate_signals({})
        assert len(signals) == 1
        assert signals[0].direction == SignalDirection.LONG

    def test_load_directory(self):
        loader = StrategyLoader()
        classes = loader.load_directory("strategies_user")
        assert len(classes) >= 3  # our 3 example strategies

    def test_registry(self):
        loader = StrategyLoader()
        loader.load_directory("strategies_user")
        all_strats = loader.list_all()
        assert "SMACrossover" in all_strats
        assert "RSIBollinger" in all_strats
        assert "MultiTFMomentum" in all_strats


# ─── Backtester Tests ───

class TestBacktester:
    def test_single_run(self):
        loader = StrategyLoader()
        loader.load_directory("strategies_user")
        cls = loader.get("SMACrossover")
        assert cls is not None

        cfg = StrategyConfig(
            name="SMA",
            symbols=["BTC/USDT"],
            timeframes=[TimeFrame.H1],
            parameters={"fast_period": 10, "slow_period": 30},
        )
        strategy = cls(cfg)
        data = {"BTC/USDT_1h": make_ohlcv(200)}

        bt = Backtester(initial_capital=10000)
        result = bt.run(strategy, data, cfg)

        assert result.strategy_name == "SMA"
        assert result.run_time_sec >= 0
        # May or may not have trades depending on synthetic data crossovers
        assert isinstance(result.equity_curve, list)
        assert isinstance(result.total_trades, int)

    def test_grid_search(self):
        loader = StrategyLoader()
        loader.load_directory("strategies_user")
        cls = loader.get("SMACrossover")

        cfg = StrategyConfig(name="SMA", symbols=["BTC/USDT"], timeframes=[TimeFrame.H1])
        data = {"BTC/USDT_1h": make_ohlcv(200)}

        bt = Backtester()
        results = bt.grid_search(cls, data, cfg, max_combinations=10)

        assert len(results) <= 10
        # Results should be sorted by PnL descending
        for i in range(len(results) - 1):
            assert results[i].total_pnl >= results[i + 1].total_pnl


# ─── Risk Manager Tests ───

class TestRiskManager:
    def test_basic_check(self):
        rm = RiskManager(RiskConfig(), initial_equity=10000)
        signal = Signal(
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            price=50000,
            stop_loss=49000,
        )
        allowed, reason, qty = rm.check_signal(signal)
        assert allowed
        assert qty > 0

    def test_kill_switch(self):
        rm = RiskManager(RiskConfig(), initial_equity=10000)
        rm.activate_kill_switch()

        signal = Signal(symbol="BTC/USDT", direction=SignalDirection.LONG, price=50000)
        allowed, reason, _ = rm.check_signal(signal)
        assert not allowed
        assert "Kill switch" in reason

    def test_drawdown_limit(self):
        cfg = RiskConfig(max_drawdown_pct=5.0)
        rm = RiskManager(cfg, initial_equity=10000)
        rm.portfolio.current_drawdown_pct = 6.0

        signal = Signal(symbol="BTC/USDT", direction=SignalDirection.LONG, price=50000)
        allowed, reason, _ = rm.check_signal(signal)
        assert not allowed

    def test_position_close(self):
        rm = RiskManager(RiskConfig(), initial_equity=10000)
        signal = Signal(
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            strategy_id="test",
            price=50000,
        )
        rm.open_position(signal, 0.1)
        pnl = rm.close_position("test", "BTC/USDT", 51000)
        assert pnl == pytest.approx(100.0)  # (51000-50000) * 0.1


# ─── Resource Manager Tests ───

class TestResourceManager:
    def test_allocation(self):
        rm = ResourceManager(total_workers=8, mode="manual")
        rm.set_allocation("strat1", priority=80)
        rm.set_allocation("strat2", priority=20)

        a1 = rm.get_allocation("strat1")
        a2 = rm.get_allocation("strat2")
        assert a1.weight > a2.weight
        assert a1.max_workers > a2.max_workers

    def test_auto_adjust(self):
        rm = ResourceManager(total_workers=4, mode="auto")
        rm.set_allocation("strat1", priority=50)
        rm.update_performance("strat1", pnl=1000, sharpe=2.0, win_rate=60)

        a = rm.get_allocation("strat1")
        assert a.priority > 50  # should have been boosted

    def test_hybrid_mode(self):
        rm = ResourceManager(total_workers=4, mode="hybrid")
        rm.set_allocation("strat1", priority=50)
        rm.update_performance("strat1", pnl=-500, sharpe=-0.5, win_rate=30)

        # Should create pending adjustment, not auto-apply
        assert len(rm.get_pending_adjustments()) > 0
        a = rm.get_allocation("strat1")
        assert a.priority == 50  # unchanged until approved


# ─── Paper Tracker Tests ───

class TestPaperTracker:
    def test_open_position_from_signal(self):
        from crypto_mega.paper.tracker import PaperTracker
        import asyncio

        tracker = PaperTracker()
        tracker.register_strategy("strat1", "TestStrategy")
        signal = Signal(
            strategy_id="strat1",
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            strength=0.8,
            price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
        )
        asyncio.get_event_loop().run_until_complete(tracker.handle_signal(signal))
        positions = tracker.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["symbol"] == "BTC/USDT"
        assert positions[0]["direction"] == "long"
        assert positions[0]["entry_price"] == 50000.0

    def test_price_update_and_pnl(self):
        from crypto_mega.paper.tracker import PaperTracker, PaperPosition

        tracker = PaperTracker()
        tracker.register_strategy("strat1", "TestStrategy")
        pos = PaperPosition(
            strategy_id="strat1",
            strategy_name="TestStrategy",
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            entry_price=50000.0,
            current_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
        )
        tracker._positions[pos.id] = pos

        # Price goes up
        tracker.update_price("BTC/USDT", 51000.0)
        assert pos.unrealized_pnl > 0
        assert pos.unrealized_pnl_pct == pytest.approx(2.0, abs=0.01)

    def test_stop_loss_trigger(self):
        from crypto_mega.paper.tracker import PaperTracker, PaperPosition

        tracker = PaperTracker()
        pos = PaperPosition(
            strategy_id="strat1",
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            entry_price=50000.0,
            stop_loss=49000.0,
        )
        tracker._positions[pos.id] = pos

        closed = tracker.update_price("BTC/USDT", 48500.0)
        assert len(closed) == 1
        assert closed[0].close_reason == "sl"
        assert closed[0].realized_pnl < 0

    def test_take_profit_trigger(self):
        from crypto_mega.paper.tracker import PaperTracker, PaperPosition

        tracker = PaperTracker()
        pos = PaperPosition(
            strategy_id="strat1",
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            entry_price=50000.0,
            take_profit=52000.0,
        )
        tracker._positions[pos.id] = pos

        closed = tracker.update_price("BTC/USDT", 52500.0)
        assert len(closed) == 1
        assert closed[0].close_reason == "tp"
        assert closed[0].realized_pnl > 0

    def test_short_position(self):
        from crypto_mega.paper.tracker import PaperTracker, PaperPosition

        tracker = PaperTracker()
        pos = PaperPosition(
            strategy_id="strat1",
            symbol="ETH/USDT",
            direction=SignalDirection.SHORT,
            entry_price=3000.0,
            stop_loss=3100.0,
            take_profit=2800.0,
        )
        tracker._positions[pos.id] = pos

        # Price drops — good for shorts
        tracker.update_price("ETH/USDT", 2900.0)
        assert pos.unrealized_pnl > 0

        # Hit TP
        closed = tracker.update_price("ETH/USDT", 2750.0)
        assert len(closed) == 1
        assert closed[0].close_reason == "tp"

    def test_leaderboard(self):
        from crypto_mega.paper.tracker import PaperTracker, PaperPosition
        from datetime import datetime, timedelta

        tracker = PaperTracker()
        tracker.register_strategy("strat_a", "WinnerStrat")
        tracker.register_strategy("strat_b", "LoserStrat")

        now = datetime.utcnow()

        # Winning closed positions for strat_a
        for i in range(5):
            pos = PaperPosition(
                strategy_id="strat_a",
                strategy_name="WinnerStrat",
                symbol="BTC/USDT",
                direction=SignalDirection.LONG,
                entry_price=50000.0,
            )
            pos.close(51000.0, "tp")
            tracker._closed.append(pos)

        # Losing closed positions for strat_b
        for i in range(5):
            pos = PaperPosition(
                strategy_id="strat_b",
                strategy_name="LoserStrat",
                symbol="BTC/USDT",
                direction=SignalDirection.LONG,
                entry_price=50000.0,
            )
            pos.close(49000.0, "sl")
            tracker._closed.append(pos)

        lb = tracker.get_leaderboard()
        assert len(lb) == 2
        assert lb[0]["strategy_name"] == "WinnerStrat"
        assert lb[0]["total_pnl_pct"] > 0
        assert lb[1]["strategy_name"] == "LoserStrat"
        assert lb[1]["total_pnl_pct"] < 0

    def test_hold_signal_ignored(self):
        from crypto_mega.paper.tracker import PaperTracker
        import asyncio

        tracker = PaperTracker()
        signal = Signal(
            strategy_id="strat1",
            symbol="BTC/USDT",
            direction=SignalDirection.HOLD,
            strength=1.0,
            price=50000.0,
        )
        asyncio.get_event_loop().run_until_complete(tracker.handle_signal(signal))
        assert len(tracker.get_open_positions()) == 0

    def test_weak_signal_ignored(self):
        from crypto_mega.paper.tracker import PaperTracker
        import asyncio

        tracker = PaperTracker()
        signal = Signal(
            strategy_id="strat1",
            symbol="BTC/USDT",
            direction=SignalDirection.LONG,
            strength=0.1,  # too weak
            price=50000.0,
        )
        asyncio.get_event_loop().run_until_complete(tracker.handle_signal(signal))
        assert len(tracker.get_open_positions()) == 0
