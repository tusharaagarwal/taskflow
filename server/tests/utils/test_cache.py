"""
Unit tests for app.utils.cache (CacheEntry, AsyncLRUCache, async_lru_cache).
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

from app.utils.cache import CacheEntry, AsyncLRUCache, async_lru_cache


class TestCacheEntry:
    """Tests for CacheEntry."""

    def test_init_without_ttl(self):
        """Entry without TTL is not expired."""
        entry = CacheEntry("value", ttl=None)
        assert entry.value == "value"
        assert entry.ttl is None

    def test_init_with_ttl(self):
        """Entry with TTL stores timestamp and ttl."""
        entry = CacheEntry("value", ttl=60)
        assert entry.value == "value"
        assert entry.ttl == 60
        assert entry.timestamp is not None

    def test_is_expired_no_ttl(self):
        """Entry with no TTL never expires."""
        entry = CacheEntry("value", ttl=None)
        assert entry.is_expired() is False

    def test_is_expired_not_expired(self):
        """Entry with TTL in future is not expired."""
        entry = CacheEntry("value", ttl=3600)
        assert entry.is_expired() is False

    def test_is_expired_expired(self):
        """Entry with TTL in past is expired."""
        entry = CacheEntry("value", ttl=1)
        entry.timestamp = datetime.now() - timedelta(seconds=10)
        assert entry.is_expired() is True


class TestAsyncLRUCache:
    """Tests for AsyncLRUCache."""

    @pytest.mark.asyncio
    async def test_get_miss(self):
        """Get returns None when key not in cache."""
        cache = AsyncLRUCache(maxsize=10)
        result = await cache.get("missing")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        """Set then get returns the value."""
        cache = AsyncLRUCache(maxsize=10)
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_expired_removes_entry(self):
        """Get on expired entry removes it and returns None."""
        cache = AsyncLRUCache(maxsize=10, ttl=0)
        await cache.set("key1", "value1")
        # Force expiry by replacing with an already-expired entry
        cache.cache["key1"].timestamp = datetime.now() - timedelta(seconds=10)
        result = await cache.get("key1")
        assert result is None
        assert "key1" not in cache.cache

    @pytest.mark.asyncio
    async def test_clear(self):
        """Clear removes all entries."""
        cache = AsyncLRUCache(maxsize=10)
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.clear()
        assert await cache.get("key1") is None
        assert await cache.get("key2") is None
        assert len(cache.cache) == 0

    @pytest.mark.asyncio
    async def test_lru_eviction_when_full(self):
        """When maxsize reached, oldest entry is evicted."""
        cache = AsyncLRUCache(maxsize=2)
        await cache.set("key1", "v1")
        await cache.set("key2", "v2")
        # Third set should evict key1 (oldest)
        await cache.set("key3", "v3")
        assert await cache.get("key1") is None
        assert await cache.get("key2") == "v2"
        assert await cache.get("key3") == "v3"

    @pytest.mark.asyncio
    async def test_set_overwrites_same_key(self):
        """Setting same key overwrites value."""
        cache = AsyncLRUCache(maxsize=10)
        await cache.set("key1", "v1")
        await cache.set("key1", "v2")
        assert await cache.get("key1") == "v2"


class TestAsyncLruCacheDecorator:
    """Tests for async_lru_cache decorator."""

    @pytest.mark.asyncio
    @patch("app.utils.cache.print")
    async def test_decorator_caches_result(self, mock_print):
        """Decorator caches and returns same result on second call."""
        call_count = 0

        @async_lru_cache(maxsize=10, ttl=None)
        async def fetch(x: int):
            nonlocal call_count
            call_count += 1
            return x * 2

        r1 = await fetch(5)
        r2 = await fetch(5)
        assert r1 == 10
        assert r2 == 10
        assert call_count == 1

    @pytest.mark.asyncio
    @patch("app.utils.cache.print")
    async def test_decorator_different_args_different_calls(self, mock_print):
        """Different args result in separate cache entries."""
        @async_lru_cache(maxsize=10)
        async def fetch(x: int):
            return x * 2

        assert await fetch(1) == 2
        assert await fetch(2) == 4
        assert await fetch(1) == 2

    @pytest.mark.asyncio
    @patch("app.utils.cache.print")
    async def test_decorator_cache_clear(self, mock_print):
        """cache_clear clears the cache."""
        @async_lru_cache(maxsize=10)
        async def fetch(x: int):
            return x

        await fetch(1)
        await fetch.cache_clear()
        # After clear, next call should recompute
        result = await fetch(1)
        assert result == 1
