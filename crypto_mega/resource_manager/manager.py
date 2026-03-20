"""Resource Manager — distributes compute across strategies based on priority and performance."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ResourceAllocation:
    """How much compute a strategy gets."""
    strategy_id: str
    priority: int = 50  # 0-100
    weight: float = 1.0  # normalized share of total compute
    max_workers: int = 1
    run_interval_sec: float = 60.0  # how often to run
    auto_adjusted: bool = False  # whether system auto-tuned this


@dataclass
class StrategyPerformance:
    """Performance metrics used for auto-adjustment."""
    strategy_id: str
    pnl: float = 0.0
    sharpe: float = 0.0
    win_rate: float = 0.0
    recent_trend: float = 0.0  # positive = improving


class ResourceManager:
    """
    Manages compute resource distribution across strategies.

    Modes:
    - MANUAL: admin sets priorities directly
    - AUTO: system adjusts based on strategy performance
    - HYBRID: system suggests, admin approves
    - RANDOM: distribute randomly (explore mode)
    """

    def __init__(self, total_workers: int = 4, mode: str = "manual"):
        self.total_workers = total_workers
        self.mode = mode
        self._allocations: dict[str, ResourceAllocation] = {}
        self._performance: dict[str, StrategyPerformance] = {}
        self._pending_adjustments: list[dict] = []

    def set_allocation(self, strategy_id: str, priority: int = 50, max_workers: int = 1) -> None:
        """Manually set resource allocation for a strategy."""
        self._allocations[strategy_id] = ResourceAllocation(
            strategy_id=strategy_id,
            priority=priority,
            max_workers=max_workers,
        )
        self._rebalance()

    def remove_allocation(self, strategy_id: str) -> None:
        self._allocations.pop(strategy_id, None)
        self._rebalance()

    def update_performance(self, strategy_id: str, pnl: float, sharpe: float, win_rate: float) -> None:
        """Update performance metrics for a strategy."""
        prev = self._performance.get(strategy_id)
        trend = (pnl - prev.pnl) if prev else 0.0

        self._performance[strategy_id] = StrategyPerformance(
            strategy_id=strategy_id,
            pnl=pnl,
            sharpe=sharpe,
            win_rate=win_rate,
            recent_trend=trend,
        )

        if self.mode in ("auto", "hybrid"):
            self._auto_adjust()

    def get_allocation(self, strategy_id: str) -> ResourceAllocation | None:
        return self._allocations.get(strategy_id)

    def get_all_allocations(self) -> dict[str, ResourceAllocation]:
        return dict(self._allocations)

    def get_pending_adjustments(self) -> list[dict]:
        """For HYBRID mode — get proposed adjustments for admin approval."""
        return list(self._pending_adjustments)

    def approve_adjustment(self, index: int) -> None:
        """Approve a pending adjustment (hybrid mode)."""
        if 0 <= index < len(self._pending_adjustments):
            adj = self._pending_adjustments.pop(index)
            alloc = self._allocations.get(adj["strategy_id"])
            if alloc:
                alloc.priority = adj["new_priority"]
                alloc.auto_adjusted = True
                self._rebalance()

    def _rebalance(self) -> None:
        """Redistribute weights based on priorities."""
        if not self._allocations:
            return

        total_priority = sum(a.priority for a in self._allocations.values())
        if total_priority == 0:
            total_priority = 1

        for alloc in self._allocations.values():
            alloc.weight = alloc.priority / total_priority
            # Distribute workers proportionally, minimum 1 if priority > 0
            alloc.max_workers = max(1, round(self.total_workers * alloc.weight))
            # Higher priority = more frequent runs
            alloc.run_interval_sec = max(10, 300 / (1 + alloc.weight * 10))

        logger.debug(f"Rebalanced {len(self._allocations)} strategies")

    def _auto_adjust(self) -> None:
        """Auto-adjust priorities based on performance."""
        for sid, perf in self._performance.items():
            alloc = self._allocations.get(sid)
            if not alloc:
                continue

            # Boost profitable, reduce unprofitable
            if perf.sharpe > 1.5 and perf.win_rate > 55:
                new_priority = min(100, alloc.priority + 10)
            elif perf.sharpe < 0 or perf.win_rate < 35:
                new_priority = max(5, alloc.priority - 10)
            elif perf.recent_trend > 0:
                new_priority = min(100, alloc.priority + 5)
            else:
                continue

            if new_priority != alloc.priority:
                adjustment = {
                    "strategy_id": sid,
                    "old_priority": alloc.priority,
                    "new_priority": new_priority,
                    "reason": f"sharpe={perf.sharpe:.2f}, wr={perf.win_rate:.1f}%, trend={perf.recent_trend:+.2f}",
                    "timestamp": time.time(),
                }

                if self.mode == "auto":
                    alloc.priority = new_priority
                    alloc.auto_adjusted = True
                    self._rebalance()
                    logger.info(f"Auto-adjusted {sid[:8]}: {adjustment['old_priority']} -> {new_priority}")
                else:  # hybrid
                    self._pending_adjustments.append(adjustment)
                    logger.info(f"Proposed adjustment for {sid[:8]}: {adjustment}")

    def get_status(self) -> dict:
        return {
            "mode": self.mode,
            "total_workers": self.total_workers,
            "allocations": {
                sid: {
                    "priority": a.priority,
                    "weight": round(a.weight, 3),
                    "workers": a.max_workers,
                    "interval": a.run_interval_sec,
                    "auto": a.auto_adjusted,
                }
                for sid, a in self._allocations.items()
            },
            "pending_adjustments": len(self._pending_adjustments),
        }
