"""
Unit tests for the abbreviation cache implementation.
"""

import pytest
import time
import threading
from unittest.mock import patch

from app.services.abbreviation_service import TTLCache, CacheEntry, CacheStats


class TestCacheEntry:
    """Tests for the CacheEntry class."""
    
    def test_cache_entry_creation(self):
        """Test creating a cache entry."""
        entry = CacheEntry(value="test_value", expiry_time=time.time() + 3600)
        
        assert entry.value == "test_value"
        assert entry.expiry_time > time.time()
        assert entry.last_access_time <= time.time()
    
    def test_cache_entry_is_expired_false(self):
        """Test that non-expired entry returns False."""
        entry = CacheEntry(value="test_value", expiry_time=time.time() + 3600)
        
        assert not entry.is_expired()
    
    def test_cache_entry_is_expired_true(self):
        """Test that expired entry returns True."""
        entry = CacheEntry(value="test_value", expiry_time=time.time() - 1)
        
        assert entry.is_expired()
    
    def test_cache_entry_touch(self):
        """Test that touch updates last access time."""
        entry = CacheEntry(value="test_value", expiry_time=time.time() + 3600)
        original_time = entry.last_access_time
        
        time.sleep(0.01)  # Small delay
        entry.touch()
        
        assert entry.last_access_time > original_time


class TestCacheStats:
    """Tests for the CacheStats class."""
    
    def test_cache_stats_creation(self):
        """Test creating cache stats."""
        stats = CacheStats()
        
        assert stats.hits == 0
        assert stats.misses == 0
        assert stats.evictions == 0
        assert stats.expirations == 0
        assert stats.invalidations == 0
        assert stats.errors == 0
        assert stats.hit_rate == 0.0
    
    def test_cache_stats_hit_rate_calculation(self):
        """Test hit rate calculation."""
        stats = CacheStats(hits=80, misses=20)
        
        assert stats.hit_rate == 0.8
    
    def test_cache_stats_hit_rate_zero_division(self):
        """Test hit rate with zero total."""
        stats = CacheStats()
        
        assert stats.hit_rate == 0.0
    
    def test_cache_stats_to_dict(self):
        """Test converting stats to dictionary."""
        stats = CacheStats(hits=10, misses=5, evictions=2)
        
        result = stats.to_dict()
        
        expected = {
            "hits": 10,
            "misses": 5,
            "evictions": 2,
            "expirations": 0,
            "invalidations": 0,
            "errors": 0,
            "hit_rate": 0.6667,
        }
        
        assert result["hits"] == expected["hits"]
        assert result["misses"] == expected["misses"]
        assert result["evictions"] == expected["evictions"]
        assert abs(result["hit_rate"] - expected["hit_rate"]) < 0.001


class TestTTLCache:
    """Tests for the TTLCache class."""
    
    def test_cache_creation(self):
        """Test creating a cache."""
        cache = TTLCache(ttl_seconds=3600, max_size=100, enabled=True)
        
        assert cache.enabled is True
        assert cache.size == 0
        assert cache._ttl_seconds == 3600
        assert cache._max_size == 100
    
    def test_cache_disabled(self):
        """Test disabled cache."""
        cache = TTLCache(enabled=False)
        
        assert cache.enabled is False
        
        # Should return None for get
        assert cache.get("key") is None
        
        # Should not store for set
        cache.set("key", "value")
        assert cache.get("key") is None
    
    def test_cache_set_and_get(self):
        """Test basic set and get operations."""
        cache = TTLCache(ttl_seconds=3600, max_size=10)
        
        cache.set("key1", "value1")
        result = cache.get("key1")
        
        assert result == "value1"
        assert cache.size == 1
    
    def test_cache_get_nonexistent(self):
        """Test getting non-existent key."""
        cache = TTLCache()
        
        result = cache.get("nonexistent")
        
        assert result is None
    
    def test_cache_get_expired(self):
        """Test getting expired entry."""
        cache = TTLCache(ttl_seconds=0.01, max_size=10)  # Very short TTL
        
        cache.set("key", "value")
        time.sleep(0.02)  # Wait for expiration
        
        result = cache.get("key")
        
        assert result is None
        assert cache.size == 0
    
    def test_cache_lru_eviction(self):
        """Test LRU eviction when max size is reached."""
        cache = TTLCache(ttl_seconds=3600, max_size=2)
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")  # Should evict key1
        
        assert cache.size == 2
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
    
    def test_cache_invalidate_all(self):
        """Test invalidating entire cache."""
        cache = TTLCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.invalidate()
        
        assert count == 2
        assert cache.size == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None
    
    def test_cache_invalidate_specific(self):
        """Test invalidating specific key."""
        cache = TTLCache()
        
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        
        count = cache.invalidate("key1")
        
        assert count == 1
        assert cache.size == 1
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
    
    def test_cache_invalidate_nonexistent(self):
        """Test invalidating non-existent key."""
        cache = TTLCache()
        
        count = cache.invalidate("nonexistent")
        
        assert count == 0
    
    def test_cache_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = TTLCache(ttl_seconds=0.01, max_size=10)
        
        cache.set("expired", "expired_value")
        time.sleep(0.02)  # Wait for first entry to expire
        cache.set("active", "active_value")  # This one should still be active
        
        # Cleanup expired entries
        cleaned_count = cache.cleanup_expired()
        
        assert cleaned_count == 1
        assert cache.get("active") == "active_value"  # Active entry should remain
        assert cache.get("expired") is None
    
    def test_cache_get_stats(self):
        """Test getting cache statistics."""
        cache = TTLCache()
        
        # Perform some operations to generate stats
        cache.get("miss1")  # Miss
        cache.set("hit1", "value1")
        cache.get("hit1")  # Hit
        
        stats = cache.get_stats()
        
        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert "max_size" in stats
        assert "ttl_seconds" in stats
        assert "enabled" in stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
    
    def test_cache_reset_stats(self):
        """Test resetting cache statistics."""
        cache = TTLCache()
        
        # Generate some stats
        cache.get("miss")
        cache.set("key", "value")
        cache.get("key")
        
        # Reset stats
        cache.reset_stats()
        
        stats = cache.get_stats()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
    
    def test_cache_thread_safety(self):
        """Test that cache operations are thread-safe."""
        cache = TTLCache(max_size=100)
        results = []
        errors = []
        
        def worker():
            try:
                for i in range(10):
                    cache.set(f"key{i}", f"value{i}")
                    result = cache.get(f"key{i}")
                    results.append(result)
            except Exception as e:
                errors.append(e)
        
        # Create multiple threads
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=worker)
            threads.append(thread)
            thread.start()
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join()
        
        # Should have no errors
        assert len(errors) == 0
        assert len(results) == 50  # 5 threads * 10 operations each
    
    def test_cache_error_handling_get(self):
        """Test error handling in get operation."""
        cache = TTLCache()
        
        # Mock the internal cache to raise an exception
        original_cache = cache._cache
        cache._cache = None
        
        # Should not raise exception
        result = cache.get("key")
        
        assert result is None
        assert cache._stats.errors == 1
        
        # Restore original cache
        cache._cache = original_cache
    
    def test_cache_error_handling_set(self):
        """Test error handling in set operation."""
        cache = TTLCache()
        
        # Mock the internal cache to raise an exception
        original_cache = cache._cache
        cache._cache = None
        
        # Should not raise exception
        cache.set("key", "value")
        
        assert cache._stats.errors == 1
        
        # Restore original cache
        cache._cache = original_cache
