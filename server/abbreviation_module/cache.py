"""
Custom TTL Cache implementation for the Abbreviation Module.

Features:
- Thread-safe operations using RLock
- Time-to-live (TTL) expiration
- LRU eviction when max size exceeded
- Global and per-key invalidation
- Performance metrics tracking
- Graceful degradation on errors
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """Statistics for cache performance monitoring."""
    
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    invalidations: int = 0
    errors: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "invalidations": self.invalidations,
            "errors": self.errors,
            "hit_rate": round(self.hit_rate, 4),
        }


@dataclass
class CacheEntry:
    """A single cache entry with value and metadata."""
    
    value: Any
    expiry_time: float
    last_access_time: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() > self.expiry_time
    
    def touch(self) -> None:
        """Update last access time for LRU tracking."""
        self.last_access_time = time.time()


class TTLCache:
    """Thread-safe TTL cache with LRU eviction.
    
    Args:
        ttl_seconds: Time-to-live for cache entries in seconds.
        max_size: Maximum number of entries in the cache.
        enabled: Whether caching is enabled.
    """
    
    def __init__(
        self,
        ttl_seconds: int = 3600,
        max_size: int = 1000,
        enabled: bool = True,
    ):
        self._ttl_seconds = ttl_seconds
        self._max_size = max_size
        self._enabled = enabled
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._stats = CacheStats()
    
    @property
    def enabled(self) -> bool:
        """Check if cache is enabled."""
        return self._enabled
    
    @property
    def size(self) -> int:
        """Get current cache size."""
        with self._lock:
            return len(self._cache)
    
    @property
    def stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._stats
    
    def get(self, key: str) -> Optional[Any]:
        """Get a value from the cache.
        
        Args:
            key: The cache key.
            
        Returns:
            The cached value if found and not expired, None otherwise.
        """
        if not self._enabled:
            self._stats.misses += 1
            return None
        
        try:
            with self._lock:
                entry = self._cache.get(key)
                
                if entry is None:
                    self._stats.misses += 1
                    return None
                
                if entry.is_expired():
                    del self._cache[key]
                    self._stats.expirations += 1
                    self._stats.misses += 1
                    return None
                
                entry.touch()
                self._stats.hits += 1
                return entry.value
                
        except Exception as e:
            logger.warning(f"Cache get error for key '{key}': {e}")
            self._stats.errors += 1
            return None
    
    def set(self, key: str, value: Any) -> None:
        """Set a value in the cache.
        
        Args:
            key: The cache key.
            value: The value to cache.
        """
        if not self._enabled:
            return
        
        try:
            with self._lock:
                # Evict if at max size
                if len(self._cache) >= self._max_size and key not in self._cache:
                    self._evict_lru()
                
                expiry_time = time.time() + self._ttl_seconds
                self._cache[key] = CacheEntry(
                    value=value,
                    expiry_time=expiry_time,
                )
                
        except Exception as e:
            logger.warning(f"Cache set error for key '{key}': {e}")
            self._stats.errors += 1
    
    def invalidate(self, key: Optional[str] = None) -> int:
        """Invalidate cache entries.
        
        Args:
            key: Specific key to invalidate. If None, invalidates all entries.
            
        Returns:
            Number of entries invalidated.
        """
        try:
            with self._lock:
                if key is None:
                    # Clear entire cache
                    count = len(self._cache)
                    self._cache.clear()
                    self._stats.invalidations += count
                    logger.info(f"Cache invalidated: cleared {count} entries")
                    return count
                else:
                    # Clear specific key
                    if key in self._cache:
                        del self._cache[key]
                        self._stats.invalidations += 1
                        logger.info(f"Cache invalidated: removed key '{key}'")
                        return 1
                    return 0
                    
        except Exception as e:
            logger.warning(f"Cache invalidation error: {e}")
            self._stats.errors += 1
            return 0
    
    def _evict_lru(self) -> None:
        """Evict the least recently used entry."""
        if not self._cache:
            return
        
        # Find LRU entry
        lru_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_access_time
        )
        
        del self._cache[lru_key]
        self._stats.evictions += 1
        logger.debug(f"Cache evicted LRU entry: '{lru_key}'")
    
    def cleanup_expired(self) -> int:
        """Remove all expired entries.
        
        Returns:
            Number of entries removed.
        """
        try:
            with self._lock:
                expired_keys = [
                    key for key, entry in self._cache.items()
                    if entry.is_expired()
                ]
                
                for key in expired_keys:
                    del self._cache[key]
                    self._stats.expirations += 1
                
                if expired_keys:
                    logger.debug(f"Cache cleanup: removed {len(expired_keys)} expired entries")
                    
                return len(expired_keys)
                
        except Exception as e:
            logger.warning(f"Cache cleanup error: {e}")
            self._stats.errors += 1
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics as a dictionary.
        
        Returns:
            Dictionary containing cache statistics.
        """
        with self._lock:
            stats_dict = self._stats.to_dict()
            stats_dict["size"] = len(self._cache)
            stats_dict["max_size"] = self._max_size
            stats_dict["ttl_seconds"] = self._ttl_seconds
            stats_dict["enabled"] = self._enabled
            return stats_dict
    
    def reset_stats(self) -> None:
        """Reset cache statistics."""
        with self._lock:
            self._stats = CacheStats()
