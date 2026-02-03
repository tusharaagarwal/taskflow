"""
Abbreviation Service - Core business logic for managing document type abbreviations.

Provides:
- Cached abbreviation retrieval
- Database lookups with graceful fallback
- Cache invalidation (global and per-key)
- Performance monitoring
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from abbreviation_module.cache import TTLCache
from abbreviation_module.config import AbbreviationConfig, get_config
from abbreviation_module.exceptions import (
    AbbreviationDatabaseError,
    AbbreviationNotFoundError,
)
from abbreviation_module.models import DocumentTypeAbbreviation

logger = logging.getLogger(__name__)


class AbbreviationService:
    """Service for managing document type abbreviations.
    
    Provides cached access to abbreviations with database fallback.
    Thread-safe for concurrent access.
    
    Usage:
        service = AbbreviationService()
        
        # Get abbreviation (uses cache, falls back to database)
        abbr = await service.get_abbreviation(db, "ANNUAL")  # Returns "ANN"
        
        # Invalidate cache after database updates
        service.invalidate_cache()  # Clear all
        service.invalidate_cache(document_type="ANNUAL")  # Clear specific
    """
    
    def __init__(self, config: Optional[AbbreviationConfig] = None):
        """Initialize the abbreviation service.
        
        Args:
            config: Optional configuration. Uses global config if not provided.
        """
        self._config = config or get_config()
        self._cache = TTLCache(
            ttl_seconds=self._config.cache.ttl_seconds,
            max_size=self._config.cache.max_size,
            enabled=self._config.cache.enabled,
        )
        logger.info(
            f"AbbreviationService initialized (cache_enabled={self._config.cache.enabled}, "
            f"ttl={self._config.cache.ttl_seconds}s, max_size={self._config.cache.max_size})"
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
            document_type: The document type to look up (e.g., "ANNUAL").
            
        Returns:
            The abbreviation string (e.g., "ANN").
            
        Raises:
            AbbreviationNotFoundError: If abbreviation not found and raise_on_not_found is True.
        """
        # Normalize document type (uppercase, trimmed)
        normalized_type = document_type.strip().upper()
        cache_key = f"abbr:{normalized_type}"
        
        # Try cache first
        cached_value = self._cache.get(cache_key)
        if cached_value is not None:
            logger.debug(f"Cache hit for document type: {normalized_type}")
            return cached_value
        
        # Cache miss - query database
        logger.debug(f"Cache miss for document type: {normalized_type}")
        
        try:
            abbreviation = await self._fetch_from_database(db, normalized_type)
            
            if abbreviation is not None:
                # Cache the result
                self._cache.set(cache_key, abbreviation)
                return abbreviation
            
            # Not found in database
            return self._handle_not_found(normalized_type)
            
        except AbbreviationNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Database error fetching abbreviation for '{normalized_type}': {e}")
            raise AbbreviationDatabaseError(
                operation="get_abbreviation",
                message=f"Failed to fetch abbreviation for '{normalized_type}': {e}"
            )
    
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
            .where(DocumentTypeAbbreviation.document_type == document_type)
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
            AbbreviationNotFoundError: If raise_on_not_found is True.
        """
        # Check fallback mappings
        if document_type in self._config.fallback_abbreviations:
            fallback = self._config.fallback_abbreviations[document_type]
            logger.warning(f"Using fallback abbreviation for '{document_type}': {fallback}")
            return fallback
        
        # Raise or return default
        if self._config.raise_on_not_found:
            raise AbbreviationNotFoundError(document_type)
        
        logger.warning(
            f"Abbreviation not found for '{document_type}', using default: {self._config.default_abbreviation}"
        )
        return self._config.default_abbreviation
    
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
            logger.error(f"Database error fetching all abbreviations: {e}")
            raise AbbreviationDatabaseError(
                operation="get_all_abbreviations",
                message=f"Failed to fetch abbreviations: {e}"
            )
    
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
            service.invalidate_cache(document_type="ANNUAL")
        """
        if document_type is None:
            count = self._cache.invalidate()
            logger.info(f"Invalidated entire abbreviation cache ({count} entries)")
            return count
        else:
            normalized_type = document_type.strip().upper()
            cache_key = f"abbr:{normalized_type}"
            count = self._cache.invalidate(cache_key)
            if count > 0:
                logger.info(f"Invalidated cache for document type: {normalized_type}")
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
