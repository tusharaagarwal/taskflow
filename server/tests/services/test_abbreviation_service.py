"""
Unit tests for the abbreviation service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.abbreviation_service import AbbreviationService, get_abbreviation_service, reset_abbreviation_service


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def config_with_fallback():
    """Create config with fallback abbreviations."""
    return {
        "cache": {
            "enabled": True,
            "ttl_seconds": 3600,
            "max_size": 100,
        },
        "fallback_abbreviations": {"unknown": "UNK"},
        "raise_on_not_found": True,
        "default_abbreviation": "DOC",
    }


@pytest.fixture
def config_no_raise():
    """Create config that doesn't raise on not found."""
    return {
        "cache": {
            "enabled": True,
            "ttl_seconds": 3600,
            "max_size": 100,
        },
        "raise_on_not_found": False,
        "default_abbreviation": "DEF",
    }


class TestAbbreviationService:
    """Tests for the AbbreviationService class."""
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_cache_hit(self, mock_db):
        """Test that cached values are returned without database query."""
        service = AbbreviationService()
        
        # Pre-populate cache
        service._cache.set("abbr:credit opinion", "CO")
        
        result = await service.get_abbreviation(mock_db, "Credit Opinion")
        
        assert result == "CO"
        # Database should not be called
        mock_db.execute.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_cache_miss_db_hit(self, mock_db):
        """Test that cache miss queries database and caches result."""
        service = AbbreviationService()
        
        # Mock database result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "CO"
        mock_db.execute.return_value = mock_result
        
        result = await service.get_abbreviation(mock_db, "Credit Opinion")
        
        assert result == "CO"
        mock_db.execute.assert_called_once()
        
        # Check it's now cached
        cached = service._cache.get("abbr:credit opinion")
        assert cached == "CO"
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_normalizes_input(self, mock_db):
        """Test that document type is normalized (lowercase, trimmed)."""
        service = AbbreviationService()
        
        # Pre-populate cache with lowercase key
        service._cache.set("abbr:credit opinion", "CO")
        
        # Query with lowercase and spaces
        result = await service.get_abbreviation(mock_db, "  credit opinion  ")
        
        assert result == "CO"
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_not_found_raises(self, mock_db):
        """Test that not found raises exception when configured."""
        service = AbbreviationService()
        
        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        with pytest.raises(ValueError) as exc_info:
            await service.get_abbreviation(mock_db, "nonexistent")
        
        assert "nonexistent" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_not_found_returns_default(self, mock_db, config_no_raise):
        """Test that not found returns default when configured."""
        service = AbbreviationService(config_no_raise)
        
        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await service.get_abbreviation(mock_db, "nonexistent")
        
        assert result == "DEF"
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_uses_fallback(self, mock_db, config_with_fallback):
        """Test that fallback is used when document type matches."""
        service = AbbreviationService(config_with_fallback)
        
        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await service.get_abbreviation(mock_db, "unknown")
        
        assert result == "UNK"
    
    def test_invalidate_cache_all(self):
        """Test invalidating entire cache."""
        service = AbbreviationService()
        service._cache.set("abbr:credit opinion", "CO")
        service._cache.set("abbr:tax", "TAX")
        
        count = service.invalidate_cache()
        
        assert count == 2
        assert service._cache.get("abbr:credit opinion") is None
        assert service._cache.get("abbr:tax") is None
    
    def test_invalidate_cache_specific(self):
        """Test invalidating specific document type."""
        service = AbbreviationService()
        service._cache.set("abbr:credit opinion", "CO")
        service._cache.set("abbr:tax", "TAX")
        
        count = service.invalidate_cache(document_type="Credit Opinion")
        
        assert count == 1
        assert service._cache.get("abbr:credit opinion") is None
        assert service._cache.get("abbr:tax") == "TAX"
    
    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        service = AbbreviationService()
        service._cache.set("abbr:credit opinion", "CO")
        
        stats = service.get_cache_stats()
        
        assert "hits" in stats
        assert "misses" in stats
        assert "size" in stats
        assert stats["size"] == 1
    
    @pytest.mark.asyncio
    async def test_get_all_abbreviations(self, mock_db):
        """Test getting all abbreviations."""
        service = AbbreviationService()
        
        # Mock database result
        mock_abbr1 = MagicMock()
        mock_abbr1.to_dict.return_value = {"document_type": "Credit Opinion", "abbreviation": "CO"}
        mock_abbr2 = MagicMock()
        mock_abbr2.to_dict.return_value = {"document_type": "TAX", "abbreviation": "TAX"}
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_abbr1, mock_abbr2]
        mock_db.execute.return_value = mock_result
        
        result = await service.get_all_abbreviations(mock_db)
        
        assert len(result) == 2
        assert result[0]["document_type"] == "Credit Opinion"
        assert result[1]["document_type"] == "TAX"


class TestGlobalService:
    """Tests for global service instance management."""
    
    def test_get_abbreviation_service_singleton(self):
        """Test that get_abbreviation_service returns same instance."""
        reset_abbreviation_service()
        
        service1 = get_abbreviation_service()
        service2 = get_abbreviation_service()
        
        assert service1 is service2
    
    def test_reset_abbreviation_service(self):
        """Test that reset creates new instance."""
        service1 = get_abbreviation_service()
        reset_abbreviation_service()
        service2 = get_abbreviation_service()
        
        assert service1 is not service2
