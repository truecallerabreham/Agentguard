"""Three-state Circuit Breaker preventing cascading infrastructure failures."""

from __future__ import annotations
import asyncio
from enum import Enum
from functools import wraps
import logging
import time
from typing import Any, Callable

from agentguard.config import ServerSettings, get_settings
from agentguard.errors import UpstreamError

logger = logging.getLogger("agentguard.reliability.circuit_breaker")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Tripped: requests fail fast without calling backend
    HALF_OPEN = "HALF_OPEN"  # Testing recovery: trial requests permitted


class CircuitBreaker:
    """Finite State Machine implementing the Circuit Breaker pattern."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 10.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._last_state_change: float = time.time()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    async def before_execution(self) -> None:
        """Inspect state before initiating downstream call; raise fast-fail error if OPEN."""
        async with self._lock:
            now = time.time()

            # 1. If OPEN, check if recovery cooldown period has expired
            if self._state == CircuitState.OPEN:
                elapsed = now - self._last_state_change
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._last_state_change = now
                    logger.info("CircuitBreaker '%s' entered HALF_OPEN state (trial request).", self.name)
                else:
                    cooldown_left = round(self.recovery_timeout - elapsed, 2)
                    raise UpstreamError(
                        code="CIRCUIT_BREAKER_OPEN",
                        hint=(
                            f"Circuit breaker for service '{self.name}' is OPEN. "
                            f"Downstream service is unhealthy; failing fast. "
                            f"Retry in {cooldown_left}s."
                        ),
                        retryable=False,
                        context={"service": self.name, "cooldown_left": cooldown_left},
                    )

    async def record_success(self) -> None:
        """Downstream call succeeded."""
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info("CircuitBreaker '%s' trial succeeded; resetting to CLOSED.", self.name)
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._last_state_change = time.time()
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self, exc: Exception) -> None:
        """Downstream call raised an exception."""
        async with self._lock:
            self._failure_count += 1
            now = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Trial call failed: trip straight back to OPEN
                logger.warning("CircuitBreaker '%s' trial failed; reverting to OPEN.", self.name)
                self._state = CircuitState.OPEN
                self._last_state_change = now
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.failure_threshold:
                    logger.error(
                        "CircuitBreaker '%s' reached threshold (%d failures); TRIPPING TO OPEN.",
                        self.name,
                        self.failure_threshold,
                    )
                    self._state = CircuitState.OPEN
                    self._last_state_change = now

    async def call(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute callable protected by the circuit breaker state machine."""
        await self.before_execution()
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as exc:
            await self.record_failure(exc)
            raise


_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    name: str,
    failure_threshold: int | None = None,
    recovery_timeout: float | None = None,
    settings: ServerSettings | None = None,
) -> CircuitBreaker:
    """Retrieve or create named CircuitBreaker singleton."""
    global _breakers
    if name not in _breakers:
        cfg = settings or get_settings()
        thresh = failure_threshold or cfg.circuit_breaker_failure_threshold
        timeout = recovery_timeout or cfg.circuit_breaker_recovery_timeout
        _breakers[name] = CircuitBreaker(name, failure_threshold=thresh, recovery_timeout=timeout)
    return _breakers[name]


def with_circuit_breaker(name: str) -> Callable:
    """Decorator to protect a function with a named Circuit Breaker."""

    def decorator(func: Callable) -> Callable:
        breaker = get_circuit_breaker(name)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator
