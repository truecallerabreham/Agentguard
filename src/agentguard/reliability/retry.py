"""Exponential backoff retry mechanism with randomized full jitter."""

from __future__ import annotations
import asyncio
from functools import wraps
import logging
import random
from typing import Any, Callable, Type

from agentguard.errors import UpstreamError

logger = logging.getLogger("agentguard.reliability.retry")


def compute_jittered_delay(attempt: int, base_delay: float = 0.1, max_delay: float = 2.0) -> float:
    """Calculate exponential backoff delay with randomized full jitter."""
    # Exponential factor: base_delay * 2^attempt
    exp_backoff = base_delay * (2 ** attempt)
    ceiling = min(max_delay, exp_backoff)
    # Full jitter: uniform random draw between 0 and ceiling
    return random.uniform(0.0, ceiling)


async def retry_async(
    func: Callable[[], Any],
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    retry_exceptions: tuple[Type[Exception], ...] = (UpstreamError,),
) -> Any:
    """Execute async callable with exponential backoff and randomized jitter on failure."""
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retry_exceptions as exc:
            if attempt == max_retries:
                logger.error("All %d retry attempts failed for %s (%s).", max_retries, func, exc)
                raise

            delay = compute_jittered_delay(attempt, base_delay, max_delay)
            logger.warning(
                "Attempt %d/%d failed with %s; backing off for %.3fs before retry.",
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 0.1,
    max_delay: float = 2.0,
    retry_exceptions: tuple[Type[Exception], ...] = (UpstreamError,),
) -> Callable:
    """Decorator to retry asynchronous operations with exponential backoff and full jitter."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            async def operation() -> Any:
                return await func(*args, **kwargs)

            return await retry_async(
                operation,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                retry_exceptions=retry_exceptions,
            )

        return wrapper

    return decorator

