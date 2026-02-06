"""
Abbreviation Service - Core business logic for managing document type abbreviations.

Provides:
- Cached abbreviation retrieval
- Database lookups with graceful fallback
- Cache invalidation (global and per-key)
- Performance monitoring
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.abbreviation import DocumentTypeAbbreviation
from app.utils.security import sanitize_log_input

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
            logger.warning(f"Cache get error for key '{sanitize_log_input(key)}': {sanitize_log_input(str(e))}")
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
            logger.warning(f"Cache set error for key '{sanitize_log_input(key)}': {sanitize_log_input(str(e))}")
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
                        logger.info(f"Cache invalidated: removed key '{sanitize_log_input(key)}'")
                        return 1
                    return 0
                    
        except Exception as e:
            logger.warning(f"Cache invalidation error: {sanitize_log_input(str(e))}")
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
        logger.debug(f"Cache evicted LRU entry: '{sanitize_log_input(lru_key)}'")
    
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
            logger.warning(f"Cache cleanup error: {sanitize_log_input(str(e))}")
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


class AbbreviationService:
    """Service for managing document type abbreviations.
    
    Provides cached access to abbreviations with database fallback.
    Thread-safe for concurrent access.
    
    Usage:
        service = AbbreviationService()
        
        # Get abbreviation (uses cache, falls back to database)
        abbr = await service.get_abbreviation(db, "Credit Opinion")  # Returns "CO"
        
        # Invalidate cache after database updates
        service.invalidate_cache()  # Clear all
        service.invalidate_cache(document_type="Credit Opinion")  # Clear specific
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the abbreviation service.
        
        Args:
            config: Optional configuration dictionary.
        """
        # Default configuration
        default_config = {
            "cache": {
                "enabled": True,
                "ttl_seconds": 3600,
                "max_size": 1000,
            },
            "fallback_abbreviations": {},
            "raise_on_not_found": True,
            "default_abbreviation": "DOC",
        }
        
        self._config = config or default_config
        cache_config = self._config.get("cache", {})
        self._cache = TTLCache(
            ttl_seconds=cache_config.get("ttl_seconds", 3600),
            max_size=cache_config.get("max_size", 1000),
            enabled=cache_config.get("enabled", True),
        )
        logger.info(
            f"AbbreviationService initialized (cache_enabled={self._cache.enabled}, "
            f"ttl={cache_config.get('ttl_seconds', 3600)}s, max_size={cache_config.get('max_size', 1000)})"
        )
    
    async def get_abbreviation(
        self,
        db: AsyncSession,
        document_type: str,
    ) -> str:
        """Get the abbreviation for a document type.
        
        Checks cache first, then falls back to database lookup.
        
        Args:
            db: Async database session.
            document_type: The document type to look up (e.g., "Credit Opinion").
            
        Returns:
            The abbreviation string (e.g., "CO").
            
        Raises:
            ValueError: If abbreviation not found and raise_on_not_found is True.
        """
        # Normalize document type (lowercase, trimmed)
        normalized_type = document_type.strip().lower()
        cache_key = f"abbr:{normalized_type}"
        
        # Try cache first
        cached_value = self._cache.get(cache_key)
        if cached_value is not None:
            logger.debug(f"Cache hit for document type: {sanitize_log_input(normalized_type)}")
            return cached_value
        
        # Cache miss - query database
        logger.debug(f"Cache miss for document type: {sanitize_log_input(normalized_type)}")
        
        try:
            abbreviation = await self._fetch_from_database(db, normalized_type)
            
            if abbreviation is not None:
                # Cache the result
                self._cache.set(cache_key, abbreviation)
                return abbreviation
            
            # Not found in database
            return self._handle_not_found(normalized_type)
            
        except ValueError:
            raise
        except Exception as e:
            s_type = sanitize_log_input(normalized_type)
            logger.error(f"Database error fetching abbreviation for '{s_type}': {sanitize_log_input(str(e))}")
            raise ValueError(f"Failed to fetch abbreviation for '{s_type}': {e}")
    
    async def _fetch_from_database(
        self,
        db: AsyncSession,
        document_type: str,
    ) -> Optional[str]:
        """Fetch abbreviation from database.
        
        Args:
            db: Async database session.
            document_type: Normalized document type.
            
        Returns:
            The abbreviation if found, None otherwise.
        """
        result = await db.execute(
            select(DocumentTypeAbbreviation.abbreviation)
            .where(func.lower(DocumentTypeAbbreviation.document_type) == document_type)
            .where(DocumentTypeAbbreviation.is_active == True)
        )
        row = result.scalar_one_or_none()
        return row
    
    def _handle_not_found(self, document_type: str) -> str:
        """Handle case when abbreviation is not found.
        
        Args:
            document_type: The document type that was not found.
            
        Returns:
            Fallback abbreviation if configured.
            
        Raises:
            ValueError: If raise_on_not_found is True.
        """
        # Check fallback mappings
        fallback_abbreviations = self._config.get("fallback_abbreviations", {})
        s_doc_type = sanitize_log_input(document_type)
        if document_type in fallback_abbreviations:
            fallback = fallback_abbreviations[document_type]
            logger.warning(f"Using fallback abbreviation for '{s_doc_type}': {sanitize_log_input(str(fallback))}")
            return fallback
        
        # Raise or return default
        if self._config.get("raise_on_not_found", True):
            raise ValueError(f"Abbreviation not found for document type: '{s_doc_type}'")
        
        default_abbreviation = self._config.get("default_abbreviation", "DOC")
        logger.warning(
            f"Abbreviation not found for '{s_doc_type}', using default: {sanitize_log_input(str(default_abbreviation))}"
        )
        return default_abbreviation
    
    async def get_all_abbreviations(
        self,
        db: AsyncSession,
        active_only: bool = True,
    ) -> List[Dict[str, Any]]:
        """Get all abbreviations from the database.
        
        Args:
            db: Async database session.
            active_only: If True, only return active abbreviations.
            
        Returns:
            List of abbreviation dictionaries.
        """
        try:
            query = select(DocumentTypeAbbreviation)
            if active_only:
                query = query.where(DocumentTypeAbbreviation.is_active == True)
            query = query.order_by(DocumentTypeAbbreviation.document_type)
            
            result = await db.execute(query)
            abbreviations = result.scalars().all()
            
            return [abbr.to_dict() for abbr in abbreviations]
            
        except Exception as e:
            logger.error(f"Database error fetching all abbreviations: {sanitize_log_input(str(e))}")
            raise ValueError(f"Failed to fetch abbreviations: {e}")
    
    def invalidate_cache(self, document_type: Optional[str] = None) -> int:
        """Invalidate cache entries.
        
        Call this method after adding or updating abbreviations in the database.
        
        Args:
            document_type: Specific document type to invalidate.
                          If None, invalidates the entire cache.
                          
        Returns:
            Number of cache entries invalidated.
            
        Examples:
            # Clear entire cache (after bulk updates)
            service.invalidate_cache()
            
            # Clear specific document type (after single update)
            service.invalidate_cache(document_type="Credit Opinion")
        """
        if document_type is None:
            count = self._cache.invalidate()
            logger.info(f"Invalidated entire abbreviation cache ({count} entries)")
            return count
        else:
            normalized_type = document_type.strip().lower()
            cache_key = f"abbr:{normalized_type}"
            count = self._cache.invalidate(cache_key)
            if count > 0:
                logger.info(f"Invalidated cache for document type: {sanitize_log_input(normalized_type)}")
            return count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics.
        
        Returns:
            Dictionary containing cache stats like hits, misses, hit_rate, etc.
        """
        return self._cache.get_stats()
    
    def cleanup_expired_cache(self) -> int:
        """Remove expired entries from cache.
        
        Can be called periodically to clean up expired entries proactively.
        
        Returns:
            Number of expired entries removed.
        """
        return self._cache.cleanup_expired()


# Global service instance for convenience
_default_service: Optional[AbbreviationService] = None


def get_abbreviation_service() -> AbbreviationService:
    """Get the global abbreviation service instance.
    
    Returns:
        AbbreviationService: The singleton service instance.
    """
    global _default_service
    if _default_service is None:
        _default_service = AbbreviationService()
    return _default_service


def reset_abbreviation_service() -> None:
    """Reset the global abbreviation service instance.
    
    Useful for testing or reconfiguration.
    """
    global _default_service
    _default_service = None
