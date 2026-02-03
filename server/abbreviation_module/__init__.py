"""
Document Type Abbreviation Module

A standalone, production-ready module for managing document type abbreviations
with database-driven storage and custom TTL caching.

Usage:
    from abbreviation_module import AbbreviationService, AbbreviationConfig
    
    # Initialize service
    service = AbbreviationService()
    
    # Get abbreviation (with caching)
    abbreviation = await service.get_abbreviation(db, "ANNUAL")  # Returns "ANN"
    
    # Invalidate cache after database updates
    service.invalidate_cache()  # Clear all
    service.invalidate_cache(document_type="ANNUAL")  # Clear specific
"""

from abbreviation_module.config import AbbreviationConfig
from abbreviation_module.service import AbbreviationService
from abbreviation_module.exceptions import (
    AbbreviationNotFoundError,
    AbbreviationCacheError,
    AbbreviationConfigError,
)

__all__ = [
    "AbbreviationService",
    "AbbreviationConfig",
    "AbbreviationNotFoundError",
    "AbbreviationCacheError",
    "AbbreviationConfigError",
]

__version__ = "1.0.0"
