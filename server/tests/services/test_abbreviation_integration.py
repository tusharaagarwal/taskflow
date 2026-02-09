"""
Integration tests for the abbreviation module.
"""

import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.abbreviation_service import AbbreviationService
from app.models.abbreviation import DocumentTypeAbbreviation


@pytest.fixture
async def mock_db_session():
    """Create a mock database session."""
    return AsyncMock()


@pytest.fixture
def sample_abbreviations():
    """Sample abbreviation data."""
    return [
        DocumentTypeAbbreviation(
            document_type="Credit Opinion",
            abbreviation="CO",
            is_active=True
        ),
        DocumentTypeAbbreviation(
            document_type="Research Update", 
            abbreviation="RU",
            is_active=True
        ),
        DocumentTypeAbbreviation(
            document_type="TAX",
            abbreviation="TAX",
            is_active=False
        ),
    ]


class TestAbbreviationIntegration:
    """Integration tests for the abbreviation module."""
    
    @pytest.mark.asyncio
    async def test_service_database_integration(self, mock_db_session, sample_abbreviations):
        """Test service integration with database."""
        service = AbbreviationService()
        
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "CO"
        mock_db_session.execute.return_value = mock_result
        
        # Test database lookup
        result = await service.get_abbreviation(mock_db_session, "Credit Opinion")
        
        assert result == "CO"
        mock_db_session.execute.assert_called_once()
        
        # Verify the query was called (we don't need to check the exact query structure)
        assert mock_db_session.execute.called
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_after_database_update(self, mock_db_session):
        """Test cache invalidation workflow."""
        service = AbbreviationService()
        
        # Pre-populate cache
        service._cache.set("abbr:credit opinion", "CO")
        assert service._cache.get("abbr:credit opinion") == "CO"
        
        # Invalidate cache (simulating database update)
        count = service.invalidate_cache(document_type="Credit Opinion")
        
        assert count == 1
        assert service._cache.get("abbr:credit opinion") is None
    
    @pytest.mark.asyncio
    async def test_get_all_abbreviations_integration(self, mock_db_session, sample_abbreviations):
        """Test get_all_abbreviations with database integration."""
        service = AbbreviationService()
        
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = sample_abbreviations
        mock_db_session.execute.return_value = mock_result
        
        # Test getting all abbreviations
        result = await service.get_all_abbreviations(mock_db_session, active_only=True)
        
        assert len(result) == 3
        assert result[0]["document_type"] == "Credit Opinion"
        assert result[0]["abbreviation"] == "CO"
        assert result[0]["is_active"] is True
        
        mock_db_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_all_abbreviations_inactive_filter(self, mock_db_session, sample_abbreviations):
        """Test get_all_abbreviations with active_only filter."""
        service = AbbreviationService()
        
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            abbr for abbr in sample_abbreviations if abbr.is_active
        ]
        mock_db_session.execute.return_value = mock_result
        
        # Test getting only active abbreviations
        result = await service.get_all_abbreviations(mock_db_session, active_only=True)
        
        assert len(result) == 2  # Only active ones
        assert all(abbr["is_active"] for abbr in result)
    
    @pytest.mark.asyncio
    async def test_fallback_abbreviation_workflow(self, mock_db_session):
        """Test fallback abbreviation workflow."""
        config = {
            "cache": {"enabled": True, "ttl_seconds": 3600, "max_size": 100},
            "fallback_abbreviations": {"unknown": "UNK"},
            "raise_on_not_found": False,
            "default_abbreviation": "DOC"
        }
        service = AbbreviationService(config)
        
        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        # Test fallback to configured abbreviation
        result = await service.get_abbreviation(mock_db_session, "unknown")
        
        assert result == "UNK"
    
    @pytest.mark.asyncio
    async def test_default_abbreviation_workflow(self, mock_db_session):
        """Test default abbreviation workflow."""
        config = {
            "cache": {"enabled": True, "ttl_seconds": 3600, "max_size": 100},
            "fallback_abbreviations": {},
            "raise_on_not_found": False,
            "default_abbreviation": "DOC"
        }
        service = AbbreviationService(config)
        
        # Mock database returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result
        
        # Test fallback to default abbreviation
        result = await service.get_abbreviation(mock_db_session, "nonexistent")
        
        assert result == "DOC"
    
    @pytest.mark.asyncio
    async def test_cache_performance_stats_tracking(self, mock_db_session):
        """Test cache performance statistics tracking."""
        service = AbbreviationService()
        
        # Mock database result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "CO"
        mock_db_session.execute.return_value = mock_result
        
        # First call - cache miss
        result1 = await service.get_abbreviation(mock_db_session, "Credit Opinion")
        assert result1 == "CO"
        
        # Second call - cache hit
        result2 = await service.get_abbreviation(mock_db_session, "Credit Opinion")
        assert result2 == "CO"
        
        # Check stats
        stats = service.get_cache_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
    
    @pytest.mark.asyncio
    async def test_cache_cleanup_maintenance(self, mock_db_session):
        """Test cache cleanup maintenance."""
        service = AbbreviationService()
        
        # Add some entries
        service._cache.set("abbr:key1", "value1")
        service._cache.set("abbr:key2", "value2")
        
        # Manually expire one entry
        expired_entry = service._cache._cache.get("abbr:key1")
        if expired_entry:
            expired_entry.expiry_time = time.time() - 1
        
        # Cleanup expired entries
        cleaned_count = service.cleanup_expired_cache()
        
        assert cleaned_count == 1
        assert service._cache.size == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_cache_access(self, mock_db_session):
        """Test concurrent access to cache."""
        import asyncio
        service = AbbreviationService()
        
        # Mock database result
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = "CO"
        mock_db_session.execute.return_value = mock_result
        
        async def worker():
            # Multiple calls from same worker
            for _ in range(5):
                result = await service.get_abbreviation(mock_db_session, "Credit Opinion")
                assert result == "CO"
        
        # Run multiple workers concurrently
        tasks = [worker() for _ in range(3)]
        await asyncio.gather(*tasks)
        
        # Should have cached the result
        assert service._cache.get("abbr:credit opinion") == "CO"
        
        # Database should only be called once (first miss)
        assert mock_db_session.execute.call_count == 1
    
    @pytest.mark.asyncio
    async def test_error_handling_database_failure(self, mock_db_session):
        """Test error handling when database fails."""
        service = AbbreviationService()
        
        # Mock database to raise exception
        mock_db_session.execute.side_effect = Exception("Database connection failed")
        
        # Should raise ValueError with database error details
        with pytest.raises(ValueError) as exc_info:
            await service.get_abbreviation(mock_db_session, "Credit Opinion")
        
        assert "Failed to fetch abbreviation" in str(exc_info.value)
    
    def test_service_configuration_validation(self):
        """Test service configuration validation."""
        # Test with invalid cache configuration
        invalid_config = {
            "cache": {"ttl_seconds": -1, "max_size": 0, "enabled": True},
            "fallback_abbreviations": {},
            "raise_on_not_found": True,
            "default_abbreviation": ""
        }
        
        # Service should still create but with validation issues
        service = AbbreviationService(invalid_config)
        
        # The service should handle invalid config gracefully
        assert service._cache.enabled is True  # Default behavior
    
    @pytest.mark.asyncio
    async def test_service_state_isolation(self, mock_db_session):
        """Test that service instances are properly isolated."""
        service1 = AbbreviationService()
        service2 = AbbreviationService()
        
        # Mock different results for each service call
        call_count = 0
        def mock_execute_side_effect(query):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = "CO"
            else:
                result.scalar_one_or_none.return_value = "RU"
            return result
        
        mock_db_session.execute.side_effect = mock_execute_side_effect
        
        # Each service should maintain its own cache
        result1 = await service1.get_abbreviation(mock_db_session, "Credit Opinion")
        result2 = await service2.get_abbreviation(mock_db_session, "Research Update")
        
        assert result1 == "CO"
        assert result2 == "RU"
        
        # Verify caches are separate
        assert service1._cache.get("abbr:credit opinion") == "CO"
        assert service2._cache.get("abbr:research update") == "RU"
        assert service1._cache.get("abbr:research update") is None
        assert service2._cache.get("abbr:credit opinion") is None
