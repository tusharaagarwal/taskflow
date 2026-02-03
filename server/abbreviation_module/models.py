"""
SQLAlchemy model for document type abbreviations.
"""

import uuid
from sqlalchemy import Boolean, Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db.database import Base


class DocumentTypeAbbreviation(Base):
    """Database model for document type abbreviations.
    
    Stores mappings between full document type names and their abbreviations.
    
    Attributes:
        id: Unique identifier (UUID).
        document_type: Full document type name (e.g., "ANNUAL", "TAX").
        abbreviation: Short abbreviation (e.g., "ANN", "TAX").
        is_active: Whether this abbreviation is active.
        created_at: Timestamp when record was created.
        updated_at: Timestamp when record was last updated.
    """
    
    __tablename__ = "document_type_abbreviations"
    
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )
    
    document_type = Column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="Full document type name (e.g., ANNUAL, TAX)",
    )
    
    abbreviation = Column(
        String(10),
        nullable=False,
        comment="Standard abbreviation (e.g., ANN, TAX)",
    )
    
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        comment="Whether this abbreviation is active",
    )
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    
    # Indexes for query optimization
    __table_args__ = (
        Index("idx_document_type_abbreviations_is_active", "is_active"),
        Index("idx_document_type_abbreviations_document_type", "document_type", unique=True),
    )
    
    def __repr__(self) -> str:
        return f"<DocumentTypeAbbreviation(document_type='{self.document_type}', abbreviation='{self.abbreviation}')>"
    
    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "document_type": self.document_type,
            "abbreviation": self.abbreviation,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
