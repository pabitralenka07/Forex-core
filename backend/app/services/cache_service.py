"""Thread-safe In-Memory TTL/LRU Cache with Request Coalescing and Stale-Serving support."""

import asyncio
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import OrderedDict
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Generic, TypeVar, cast

from app.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Internal cache entry storing payload, timestamp, and expiration."""

    key: str
    value: T
    created_at: float  # Unix epoch seconds (wall clock)
    expires_at: float  # monotonic seconds for high-resolution expiration

    def is_stale(self, current_monotonic: float) -> bool:
        return current_monotonic > self.expires_at

    def age_seconds(self, current_wall_clock: float) -> int:
        return max(0, int(current_wall_clock - self.created_at))


class BaseCache(ABC):
    """Abstract caching interface supporting pluggable backends (memory, redis)."""

    @abstractmethod
    async def get(self, key: str, allow_stale: bool = False) -> tuple[Any | None, bool, int]:
        """Retrieve item from cache.

        Returns:
            Tuple of (value, is_stale, age_seconds). If key missing or expired
            (with allow_stale=False), value is None.
        """
        ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        """Store item in cache with specific TTL."""
        ...

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries."""
        ...


class InMemoryTTLCache(BaseCache):
    """Thread-safe, async-safe in-memory cache with TTL expiration and LRU capacity eviction."""

    def __init__(self, max_size: int = 1000, default_ttl: float = 3600.0) -> None:
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._entries: OrderedDict[str, CacheEntry[Any]] = OrderedDict()
        self._thread_lock = threading.Lock()
        self._async_lock = asyncio.Lock()
        # Request coalescing (single-flight) map: key -> running asyncio.Task
        self._in_flight: dict[str, asyncio.Task[Any]] = {}

    async def get(self, key: str, allow_stale: bool = False) -> tuple[Any | None, bool, int]:
        now_mono = time.monotonic()
        now_wall = time.time()

        with self._thread_lock:
            entry = self._entries.get(key)
            if entry is None:
                return None, False, 0

            # Move to end for LRU tracking
            self._entries.move_to_end(key)

            stale = entry.is_stale(now_mono)
            age = entry.age_seconds(now_wall)

            if stale and not allow_stale:
                return None, False, 0

            return entry.value, stale, age

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        now_mono = time.monotonic()
        now_wall = time.time()
        expires_at = now_mono + ttl

        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now_wall,
            expires_at=expires_at,
        )

        with self._thread_lock:
            # If replacing existing key, move to end
            if key in self._entries:
                self._entries.move_to_end(key)
            self._entries[key] = entry

            # LRU eviction if size limit exceeded
            if len(self._entries) > self.max_size:
                evicted_key, _ = self._entries.popitem(last=False)
                logger.debug("LRU evicted oldest cache key: %s", evicted_key)

    async def clear(self) -> None:
        with self._thread_lock:
            self._entries.clear()

    async def coalesce(
        self,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, T]],
    ) -> T:
        """Request Coalescing (Single-Flight).

        If multiple concurrent tasks request the same key simultaneously,
        only one upstream fetch task runs; all other callers await the exact same task.
        """
        async with self._async_lock:
            if key in self._in_flight:
                task = self._in_flight[key]
            else:
                task = asyncio.create_task(fetcher())
                self._in_flight[key] = task

        try:
            result = await task
            return cast(T, result)
        finally:
            async with self._async_lock:
                if key in self._in_flight and self._in_flight[key] is task:
                    del self._in_flight[key]


# Global cache singleton instance
_cache_singleton: InMemoryTTLCache | None = None


def get_cache_service() -> InMemoryTTLCache:
    """Return the global cache service singleton."""
    global _cache_singleton
    if _cache_singleton is None:
        settings = get_settings()
        _cache_singleton = InMemoryTTLCache(
            max_size=settings.cache_max_size,
            default_ttl=float(settings.cache_ttl_seconds),
        )
    return _cache_singleton
