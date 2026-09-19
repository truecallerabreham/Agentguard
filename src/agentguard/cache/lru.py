"""In-memory L1 Least Recently Used (LRU) cache with time-to-live (TTL) expiration."""

from __future__ import annotations
from collections import OrderedDict
import time
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class LRUCache(Generic[T]):
    """Fast, in-process Least Recently Used (LRU) cache with per-item TTL expiration."""

    def __init__(self, maxsize: int = 1000, default_ttl: float = 30.0) -> None:
        self.maxsize = maxsize
        self.default_ttl = default_ttl
        # OrderedDict maintains insertion/access order: oldest item at the beginning
        self._cache: OrderedDict[str, tuple[T, float]] = OrderedDict()

    def get(self, key: str) -> T | None:
        """Retrieve item if present and unexpired, updating its LRU position."""
        if key not in self._cache:
            return None

        val, expire_at = self._cache[key]
        now = time.time()

        # Check for expiration
        if now > expire_at:
            del self._cache[key]
            return None

        # Move to end to mark as recently accessed
        self._cache.move_to_end(key)
        return val

    def set(self, key: str, value: T, ttl: float | None = None) -> None:
        """Store item with expiration; evict oldest item if capacity is exceeded."""
        effective_ttl = ttl if ttl is not None else self.default_ttl
        expire_at = time.time() + effective_ttl

        if key in self._cache:
            del self._cache[key]
        elif len(self._cache) >= self.maxsize:
            # Evict least recently used (first item)
            self._cache.popitem(last=False)

        self._cache[key] = (value, expire_at)

    def delete(self, key: str) -> bool:
        """Remove a key from the cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def size(self) -> int:
        """Return the current number of items (including any unpruned expired items)."""
        return len(self._cache)

    def prune_expired(self) -> int:
        """Evict expired items and return count of pruned entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]
        return len(expired)

