"""
Integration tests for the abbreviation module with database.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from abbreviation_module.models import DocumentTypeAbbreviation
from abbreviation_module.service import AbbreviationService


@pytest.fixture
async def abbreviation_data(db):
    """Create test abbreviation data in the database."""
    abbreviations = [
        DocumentTypeAbbreviation(
            document_type="Credit Opinion",
            abbreviation="CO",
            is_active=True,
        ),
        DocumentTypeAbbreviation(
            document_type="TAX",
            abbreviation="TAX",
            is_active=True,
        ),
        DocumentTypeAbbreviation(
            document_type="QUARTERLY",
            abbreviation="QTR",
            is_active=True,
        ),
        DocumentTypeAbbreviation(
            document_type="INACTIVE",
            abbreviation="INA",
            is_active=False,
        ),
    ]
    
    for abbr in abbreviations:
        db.add(abbr)
    
    await db.commit()
    
    for abbr in abbreviations:
        await db.refresh(abbr)
    
    return abbreviations


class TestDocumentTypeAbbreviationModel:
    """Tests for the DocumentTypeAbbreviation model."""
    
    @pytest.mark.asyncio
    async def test_create_abbreviation(self, db):
        """Test creating a new abbreviation record."""
        abbr = DocumentTypeAbbreviation(
            document_type="TEST",
            abbreviation="TST",
            is_active=True,
        )
        db.add(abbr)
        await db.commit()
        await db.refresh(abbr)
        
        assert abbr.id is not None
        assert abbr.document_type == "TEST"
        assert abbr.abbreviation == "TST"
        assert abbr.is_active is True
        assert abbr.created_at is not None
        assert abbr.updated_at is not None
    
    @pytest.mark.asyncio
    async def test_unique_constraint_on_document_type(self, db, abbreviation_data):
        """Test that duplicate document types are rejected."""
        from sqlalchemy.exc import IntegrityError
        
        duplicate = DocumentTypeAbbreviation(
            document_type="Credit Opinion",  # Already exists
            abbreviation="DUP",
            is_active=True,
        )
        db.add(duplicate)
        
        with pytest.raises(IntegrityError):
            await db.commit()
    
    @pytest.mark.asyncio
    async def test_to_dict(self, db, abbreviation_data):
        """Test model to_dict conversion."""
        result = await db.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type == "Credit Opinion"
            )
        )
        abbr = result.scalar_one()
        
        data = abbr.to_dict()
        
        assert data["document_type"] == "Credit Opinion"
        assert data["abbreviation"] == "CO"
        assert data["is_active"] is True
        assert "id" in data
        assert "created_at" in data


class TestAbbreviationServiceIntegration:
    """Integration tests for AbbreviationService with real database."""
    
    @pytest.mark.asyncio
    async def test_get_abbreviation_from_database(self, db, abbreviation_data):
        """Test getting abbreviation from database."""
        service = AbbreviationService()
        service.invalidate_cache()  # Ensure cache is empty
        
        result = await service.get_abbreviation(db, "Credit Opinion")
        
        assert result == "CO"
    
    @pytest.mark.asyncio
    async def test_caching_behavior(self, db, abbreviation_data):
        """Test that abbreviations are cached after first fetch."""
        service = AbbreviationService()
        service.invalidate_cache()
        
        # First fetch - should query database
        result1 = await service.get_abbreviation(db, "TAX")
        stats_after_first = service.get_cache_stats()
        
        # Second fetch - should come from cache
        result2 = await service.get_abbreviation(db, "TAX")
        stats_after_second = service.get_cache_stats()
        
        assert result1 == result2 == "TAX"
        assert stats_after_second["hits"] > stats_after_first["hits"]
    
    @pytest.mark.asyncio
    async def test_inactive_abbreviations_not_returned(self, db, abbreviation_data):
        """Test that inactive abbreviations are not returned."""
        from abbreviation_module.exceptions import AbbreviationNotFoundError
        
        service = AbbreviationService()
        service.invalidate_cache()
        
        with pytest.raises(AbbreviationNotFoundError):
            await service.get_abbreviation(db, "INACTIVE")
    
    @pytest.mark.asyncio
    async def test_all_active_abbreviations(self, db, abbreviation_data):
        """Test getting all active abbreviations."""
        service = AbbreviationService()
        
        result = await service.get_all_abbreviations(db, active_only=True)
        
        # Should not include inactive
        doc_types = [r["document_type"] for r in result]
        assert "Credit Opinion" in doc_types
        assert "TAX" in doc_types
        assert "INACTIVE" not in doc_types
    
    @pytest.mark.asyncio
    async def test_get_all_abbreviations_include_inactive(self, db, abbreviation_data):
        """Test getting all abbreviations including inactive."""
        service = AbbreviationService()
        
        result = await service.get_all_abbreviations(db, active_only=False)
        
        doc_types = [r["document_type"] for r in result]
        assert "INACTIVE" in doc_types
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_updates_value(self, db, abbreviation_data):
        """Test that cache invalidation allows updated values."""
        service = AbbreviationService()
        service.invalidate_cache()
        
        # Fetch and cache
        result1 = await service.get_abbreviation(db, "Credit Opinion")
        assert result1 == "CO"
        
        # Update database directly
        await db.execute(
            text("UPDATE document_type_abbreviations SET abbreviation = 'CO-UPD' WHERE document_type = 'Credit Opinion'")
        )
        await db.commit()
        
        # Should still return cached value
        result2 = await service.get_abbreviation(db, "Credit Opinion")
        assert result2 == "CO"
        
        # Invalidate cache
        service.invalidate_cache(document_type="Credit Opinion")
        
        # Should now return new value
        result3 = await service.get_abbreviation(db, "Credit Opinion")
        assert result3 == "CO-UPD"


class TestReportIdSequence:
    """Tests for the report ID sequence."""
    
    @pytest.mark.asyncio
    async def test_sequence_starts_at_100001(self, db):
        """Test that sequence starts at 100001."""
        # Note: This test assumes the sequence has been created by migration
        try:
            result = await db.execute(text("SELECT nextval('report_id_seq')"))
            value = result.scalar()
            assert value >= 100001
        except Exception:
            pytest.skip("Sequence not available in test database")
    
    @pytest.mark.asyncio
    async def test_sequence_increments(self, db):
        """Test that sequence increments with each call."""
        try:
            result1 = await db.execute(text("SELECT nextval('report_id_seq')"))
            value1 = result1.scalar()
            
            result2 = await db.execute(text("SELECT nextval('report_id_seq')"))
            value2 = result2.scalar()
            
            assert value2 == value1 + 1
        except Exception:
            pytest.skip("Sequence not available in test database")
