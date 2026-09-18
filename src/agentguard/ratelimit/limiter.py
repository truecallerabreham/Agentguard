"""Distributed token-bucket rate limiter with Redis Lua script and in-memory fallback."""

from __future__ import annotations
import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import time
from typing import Any
import redis.asyncio as aioredis

from agentguard.config import ServerSettings, get_settings

logger = logging.getLogger("agentguard.ratelimit")

LUA_PATH = Path(__file__).parent / "token_bucket.lua"


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after: float
    capacity: int


class RateLimiter:
    """Enforces token-bucket quotas per-tenant and per-agent atomically."""

    def __init__(self, settings: ServerSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._redis: aioredis.Redis | None = None
        self._lua_sha: str | None = None
        self._lua_code: str = ""
        self._is_fallback: bool = False
        self._initialized: bool = False
        self._mem_buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_refreshed)
        self._lock = asyncio.Lock()

        if LUA_PATH.is_file():
            self._lua_code = LUA_PATH.read_text(encoding="utf-8")

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    async def initialize(self) -> None:
        """Attempt connection to Redis. Fall back to thread-safe in-memory simulator if unreachable."""
        if self._initialized:
            return
        self._initialized = True

        try:
            client = aioredis.from_url(
                self.settings.redis_url,
                socket_connect_timeout=1.5,
                decode_responses=True,
            )
            await client.ping()
            self._redis = client
            if self._lua_code:
                self._lua_sha = await self._redis.script_load(self._lua_code)
            self._is_fallback = False
            logger.info("Connected to Redis distributed rate limiter.")
        except Exception as exc:
            self._redis = None
            self._is_fallback = True
            logger.warning(
                "Redis unreachable at %s (%s). Using in-memory token bucket simulator.",
                self.settings.redis_url,
                exc,
            )

    async def close(self) -> None:
        """Close connection to Redis."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._initialized = False

    async def check(
        self,
        key: str,
        cost: int = 1,
        capacity: int | None = None,
        refill_rate: float | None = None,
    ) -> RateLimitResult:
        """Check and decrement quota for the given key atomically."""
        if not self.settings.rate_limit_enabled:
            return RateLimitResult(allowed=True, remaining=999, retry_after=0.0, capacity=999)

        if not self._initialized:
            await self.initialize()

        cap = capacity or self.settings.rate_limit_capacity
        rate = refill_rate or self.settings.rate_limit_refill_rate
        now = time.time()

        # 1. Distributed Redis with atomic Lua script
        if self._redis is not None and self._lua_sha is not None:
            try:
                res = await self._redis.evalsha(
                    self._lua_sha,
                    1,
                    key,
                    cap,
                    rate,
                    now,
                    cost,
                )
                allowed = bool(res[0])
                remaining = int(res[1])
                retry_after = float(res[2])
                return RateLimitResult(
                    allowed=allowed,
                    remaining=remaining,
                    retry_after=retry_after,
                    capacity=cap,
                )
            except Exception as exc:
                logger.warning("Redis evalsha failed (%s). Falling back to in-memory check.", exc)

        # 2. In-Memory Token Bucket Simulator
        async with self._lock:
            if key not in self._mem_buckets:
                tokens = float(cap)
                last_refreshed = now
            else:
                tokens, last_refreshed = self._mem_buckets[key]
                elapsed = max(0.0, now - last_refreshed)
                tokens = min(float(cap), tokens + (elapsed * rate))
                last_refreshed = now

            if tokens >= cost:
                tokens -= cost
                self._mem_buckets[key] = (tokens, last_refreshed)
                return RateLimitResult(
                    allowed=True,
                    remaining=int(tokens),
                    retry_after=0.0,
                    capacity=cap,
                )
            else:
                needed = cost - tokens
                retry_after = needed / rate
                self._mem_buckets[key] = (tokens, last_refreshed)
                return RateLimitResult(
                    allowed=False,
                    remaining=int(tokens),
                    retry_after=round(retry_after, 2),
                    capacity=cap,
                )


_rate_limiter: RateLimiter | None = None


def get_rate_limiter(settings: ServerSettings | None = None) -> RateLimiter:
    """Singleton getter for RateLimiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(settings)
    return _rate_limiter
