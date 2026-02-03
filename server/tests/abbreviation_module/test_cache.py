"""
Unit tests for the TTL cache implementation.
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from abbreviation_module.cache import TTLCache, CacheStats, CacheEntry


class TestCacheEntry:
    """Tests for the CacheEntry dataclass."""
    
    def test_is_expired_false(self):
        """Test that entry is not expired when expiry time is in future."""
        entry = CacheEntry(value="test", expiry_time=time.time() + 3600)
        assert entry.is_expired() is False
    
    def test_is_expired_true(self):
        """Test that entry is expired when expiry time is in past."""
        entry = CacheEntry(value="test", expiry_time=time.time() - 1)
        assert entry.is_expired() is True
    
    def test_touch_updates_access_time(self):
        """Test that touch() updates last_access_time."""
        entry = CacheEntry(value="test", expiry_time=time.time() + 3600)
        original_time = entry.last_access_time
        time.sleep(0.01)
        entry.touch()
        assert entry.last_access_time > original_time


class TestCacheStats:
    """Tests for the CacheStats dataclass."""
    
    def test_hit_rate_with_hits_and_misses(self):
        """Test hit rate calculation with both hits and misses."""
        stats = CacheStats(hits=75, misses=25)
        assert stats.hit_rate == 0.75
    
    def test_hit_rate_with_no_accesses(self):
        """Test hit rate is 0 when no accesses."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        stats = CacheStats(hits=10, misses=5)
        result = stats.to_dict()
        assert result["hits"] == 10
        assert result["misses"] == 5
        assert "hit_rate" in result


class TestTTLCache:
    """Tests for the TTLCache class."""
    
    def test_basic_get_set(self):
        """Test basic get and set operations."""
        cache = TTLCache(ttl_seconds=60)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
    
    def test_get_nonexistent_key(self):
        """Test that getting nonexistent key returns None."""
        cache = TTLCache()
        assert cache.get("nonexistent") is None
    
    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = TTLCache(ttl_seconds=0)  # Immediate expiration
        cache.set("key1", "value1")
        time.sleep(0.01)  # Small delay to ensure expiration
        assert cache.get("key1") is None
        assert cache.stats.expirations >= 1
    
    def test_lru_eviction(self):
        """Test LRU eviction when max size exceeded."""
        cache = TTLCache(ttl_seconds=3600, max_size=2)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        # Access key1 to make it more recently used
        cache.get("key1")
        
        # Add key3, should evict key2 (LRU)
        cache.set("key3", "value3")
        
        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None  # Should be evicted
        assert cache.get("key3") == "value3"
        assert cache.stats.evictions >= 1
    
    def test_invalidate_all(self):
        """Test invalidating entire cache."""
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.invalidate()
        
        assert count == 2
        assert cache.get("key1") is None
        assert cache.get("key2") is None
        assert cache.size == 0
    
    def test_invalidate_specific_key(self):
        """Test invalidating specific key."""
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.invalidate("key1")
        
        assert count == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
    
    def test_invalidate_nonexistent_key(self):
        """Test invalidating nonexistent key returns 0."""
        cache = TTLCache(ttl_seconds=3600)
        count = cache.invalidate("nonexistent")
        assert count == 0
    
    def test_disabled_cache(self):
        """Test cache operations when disabled."""
        cache = TTLCache(enabled=False)
        cache.set("key1", "value1")
        assert cache.get("key1") is None
        assert cache.size == 0
    
    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        cache = TTLCache(ttl_seconds=0)  # Immediate expiration
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        time.sleep(0.01)
        
        count = cache.cleanup_expired()
        
        assert count == 2
        assert cache.size == 0
    
    def test_get_stats(self):
        """Test getting cache statistics."""
        cache = TTLCache(ttl_seconds=3600, max_size=100)
        cache.set("key1", "value1")
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss
        
        stats = cache.get_stats()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 3600
        assert stats["enabled"] is True
    
    def test_reset_stats(self):
        """Test resetting cache statistics."""
        cache = TTLCache(ttl_seconds=3600)
        cache.set("key1", "value1")
        cache.get("key1")
        
        cache.reset_stats()
        
        assert cache.stats.hits == 0
        assert cache.stats.misses == 0
    
    def test_thread_safety(self):
        """Test thread safety with concurrent operations."""
        cache = TTLCache(ttl_seconds=3600, max_size=1000)
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(100):
                    key = f"key_{worker_id}_{i}"
                    cache.set(key, f"value_{i}")
                    cache.get(key)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(10):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        assert len(errors) == 0


class TestCachePerformance:
    """Performance tests for the cache."""
    
    def test_cache_lookup_performance(self):
        """Test that cache lookups are fast."""
        cache = TTLCache(ttl_seconds=3600, max_size=10000)
        
        # Populate cache
        for i in range(1000):
            cache.set(f"key_{i}", f"value_{i}")
        
        # Measure lookup time
        start = time.perf_counter()
        for i in range(1000):
            cache.get(f"key_{i}")
        elapsed = time.perf_counter() - start
        
        # Should complete in under 50ms (very generous limit)
        assert elapsed < 0.05, f"Cache lookups took {elapsed:.3f}s"
