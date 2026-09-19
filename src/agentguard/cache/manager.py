"""Two-tier caching manager (L1 in-process LRU + L2 Redis) with single-flight stampede protection."""

from __future__ import annotations
import asyncio
from functools import wraps
import hashlib
import json
import logging
import time
from typing import Any, Callable, Coroutine
import redis.asyncio as aioredis

from agentguard.cache.lru import LRUCache
from agentguard.config import ServerSettings, get_settings
from agentguard.governance.tenant import current_tenant

logger = logging.getLogger("agentguard.cache")


def make_cache_key(tenant: str, tool_name: str, arguments: dict[str, Any] | None = None) -> str:
    """Create a deterministic, tenant-partitioned cache key using SHA-256."""
    canonical_json = json.dumps(arguments or {}, sort_keys=True, default=str)
    digest = hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()[:16]
    return f"cache:{tenant}:{tool_name}:{digest}"


class CacheManager:
    """Orchestrates L1 LRU and L2 Redis caching with single-flight thundering herd defense."""

    def __init__(self, settings: ServerSettings | None = None) -> None:
        self.settings = settings or get_settings()
        self._l1: LRUCache[Any] = LRUCache(
            maxsize=self.settings.cache_l1_capacity,
            default_ttl=float(self.settings.cache_l1_ttl_seconds),
        )
        self._redis: aioredis.Redis | None = None
        self._is_fallback: bool = False
        self._initialized: bool = False

        # Single-Flight synchronization structures
        self._flight_locks: dict[str, asyncio.Lock] = {}
        self._master_lock = asyncio.Lock()

        # Telemetry metrics
        self.l1_hits: int = 0
        self.l2_hits: int = 0
        self.misses: int = 0

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    async def initialize(self) -> None:
        """Connect to Redis for L2 caching. Fall back to L1 only if unreachable."""
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
            self._is_fallback = False
            logger.info("Connected to Redis L2 distributed cache.")
        except Exception as exc:
            self._redis = None
            self._is_fallback = True
            logger.warning(
                "Redis unreachable at %s (%s). Running with L1 LRU cache only.",
                self.settings.redis_url,
                exc,
            )

    async def close(self) -> None:
        """Close connection to Redis."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._initialized = False

    async def get(self, key: str) -> Any | None:
        """Query L1 and L2 caches in order."""
        if not self.settings.cache_enabled:
            return None

        # 1. Check L1 in-memory LRU cache (<0.1ms)
        l1_val = self._l1.get(key)
        if l1_val is not None:
            self.l1_hits += 1
            return l1_val

        # 2. Check L2 distributed Redis cache
        if not self._initialized:
            await self.initialize()

        if self._redis is not None:
            try:
                raw = await self._redis.get(key)
                if raw is not None:
                    val = json.loads(raw)
                    # Backfill L1 cache from L2
                    self._l1.set(key, val, ttl=float(self.settings.cache_l1_ttl_seconds))
                    self.l2_hits += 1
                    return val
            except Exception as exc:
                logger.warning("Redis L2 cache read error (%s)", exc)

        self.misses += 1
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl_l1: float | None = None,
        ttl_l2: int | None = None,
    ) -> None:
        """Write item to both L1 and L2 caches."""
        if not self.settings.cache_enabled:
            return

        effective_l1 = ttl_l1 or float(self.settings.cache_l1_ttl_seconds)
        effective_l2 = ttl_l2 or self.settings.cache_l2_ttl_seconds

        # Store in L1
        self._l1.set(key, value, ttl=effective_l1)

        # Store in L2 Redis
        if not self._initialized:
            await self.initialize()

        if self._redis is not None:
            try:
                serialized = json.dumps(value, default=str)
                await self._redis.set(key, serialized, ex=effective_l2)
            except Exception as exc:
                logger.warning("Redis L2 cache write error (%s)", exc)

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Coroutine[Any, Any, Any]],
        ttl_l1: float | None = None,
        ttl_l2: int | None = None,
    ) -> Any:
        """Retrieve from cache or compute once using single-flight mutex protection."""
        # Fast path: check cache before locking
        cached = await self.get(key)
        if cached is not None:
            return cached

        # Acquire or create per-key flight lock
        async with self._master_lock:
            if key not in self._flight_locks:
                self._flight_locks[key] = asyncio.Lock()
            flight_lock = self._flight_locks[key]

        async with flight_lock:
            # Double-check cache inside lock: another concurrent flight may have just finished!
            cached = await self.get(key)
            if cached is not None:
                return cached

            # We are the designated flight: compute the expensive result
            result = await compute_fn()
            await self.set(key, result, ttl_l1=ttl_l1, ttl_l2=ttl_l2)
            return result

        # Cleanup flight lock
        async with self._master_lock:
            if key in self._flight_locks and not self._flight_locks[key].locked():
                del self._flight_locks[key]


_cache_manager: CacheManager | None = None


def get_cache_manager(settings: ServerSettings | None = None) -> CacheManager:
    """Singleton getter for CacheManager."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager(settings)
    return _cache_manager


def cached_tool(
    ttl_l1: float | None = None,
    ttl_l2: int | None = None,
) -> Callable:
    """Decorator to apply two-tier caching and stampede prevention to a tool function."""

    def decorator(func: Callable) -> Callable:
        tool_name = func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            settings = get_settings()
            if not settings.cache_enabled:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            tenant = current_tenant.get() or "default"
            cache_key = make_cache_key(tenant, tool_name, kwargs)
            manager = get_cache_manager(settings)

            async def compute() -> Any:
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)

            return await manager.get_or_compute(cache_key, compute, ttl_l1=ttl_l1, ttl_l2=ttl_l2)

        return async_wrapper

    return decorator

