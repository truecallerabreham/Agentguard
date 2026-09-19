"""Adaptive Timeout Budget Allocation (ATBA) for multi-step agent tool execution."""

from __future__ import annotations
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import time
from typing import Any, Callable

from agentguard.errors import UpstreamError

current_budget: ContextVar[TimeoutBudget | None] = ContextVar("current_budget", default=None)


@dataclass
class TimeoutBudget:
    """Tracks elapsed time and remaining budget across multi-step execution flows."""

    total_seconds: float
    start_time: float
    deadline: float

    @classmethod
    def start(cls, seconds: float) -> TimeoutBudget:
        now = time.time()
        return cls(total_seconds=seconds, start_time=now, deadline=now + seconds)

    @property
    def remaining(self) -> float:
        """Seconds remaining before deadline (clamped at 0.0)."""
        return max(0.0, self.deadline - time.time())

    @property
    def is_exhausted(self) -> bool:
        return self.remaining <= 0.0

    def allocate_step_timeout(self, max_step_timeout: float = 10.0) -> float:
        """Calculate maximum allowable timeout for the next individual step within the remaining budget."""
        if self.is_exhausted:
            raise UpstreamError(
                code="TIMEOUT_BUDGET_EXHAUSTED",
                hint=(
                    f"Overall SLA timeout budget of {self.total_seconds}s has been exhausted. "
                    "Halting downstream operations to prevent cascading SLA breach."
                ),
                retryable=True,
                context={"total_budget": self.total_seconds, "remaining": 0.0},
            )
        return min(max_step_timeout, self.remaining)


class BudgetContext:
    """Async context manager that scopes a TimeoutBudget across coroutines."""

    def __init__(self, seconds: float) -> None:
        self.budget = TimeoutBudget.start(seconds)
        self._token = None

    async def __aenter__(self) -> TimeoutBudget:
        self._token = current_budget.set(self.budget)
        return self.budget

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token is not None:
            current_budget.reset(self._token)

