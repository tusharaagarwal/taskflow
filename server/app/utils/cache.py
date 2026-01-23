import asyncio
import functools
from datetime import datetime, timedelta
from typing import Any, Callable, Optional


class CacheEntry:
    """Represents a single cache entry with optional TTL."""
    
    def __init__(self, value: Any, ttl: Optional[int] = None):
        self.value = value
        self.timestamp = datetime.now()
        self.ttl = ttl
    
    def is_expired(self) -> bool:
        """Check if this cache entry has expired."""
        if self.ttl is None:
            return False
        expiry_time = self.timestamp + timedelta(seconds=self.ttl)
        return datetime.now() > expiry_time


class AsyncLRUCache:
    """Thread-safe async LRU cache with TTL support."""
    
    def __init__(self, maxsize: int = 128, ttl: Optional[int] = None):
        """
        Initialize the async LRU cache.
        
        Args:
            maxsize: Maximum number of cached results (LRU eviction after this)
            ttl: Time to live in seconds (None = no expiration)
        """
        self.maxsize = maxsize
        self.ttl = ttl
        self.cache = {}
        self.lock = asyncio.Lock()
    
    async def get(self, key: str) -> Optional[Any]:
        """Get a value from cache if it exists and hasn't expired."""
        async with self.lock:
            if key in self.cache:
                entry = self.cache[key]
                if not entry.is_expired():
                    return entry.value
                else:
                    del self.cache[key]
        return None
    
    async def set(self, key: str, value: Any) -> None:
        """Set a value in cache, removing oldest entry if maxsize is reached."""
        async with self.lock:
            if len(self.cache) >= self.maxsize:
                # Remove oldest entry (LRU)
                oldest_key = min(self.cache.keys(), 
                               key=lambda k: self.cache[k].timestamp)
                del self.cache[oldest_key]
            
            self.cache[key] = CacheEntry(value, self.ttl)
    
    async def clear(self) -> None:
        """Clear all cache entries."""
        async with self.lock:
            self.cache.clear()


def async_lru_cache(maxsize: int = 128, ttl: Optional[int] = None):
    """
    Decorator for async functions that caches results with TTL support.
    
    Args:
        maxsize: Maximum number of cached results (LRU eviction after this)
        ttl: Time to live in seconds (None = no expiration)
    
    Example:
        @async_lru_cache(maxsize=100, ttl=1800)
        async def get_by_report_id(db: AsyncSession, report_id: str):
            # function implementation
            pass
    """
    cache = AsyncLRUCache(maxsize=maxsize, ttl=ttl)
    
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key from function name and arguments
            # Convert unhashable types to strings for key generation
            args_str = str(args)
            kwargs_str = str(sorted(kwargs.items()))
            cache_key = f"{func.__name__}:{args_str}:{kwargs_str}"
            
            # Check cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                print(f"[CACHE HIT] {func.__name__} - Key: {cache_key[:50]}...")
                return cached_value
            
            # Call actual function
            result = await func(*args, **kwargs)
            
            # Store in cache
            await cache.set(cache_key, result)
            print(f"[CACHE SET] {func.__name__} - Key: {cache_key[:50]}...")
            return result
        
        # Add cache control methods
        wrapper.cache_clear = cache.clear
        return wrapper
    
    return decorator

