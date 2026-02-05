from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID


class DocumentTypeAbbreviationCreateRequest(BaseModel):
    """Request schema for creating a new document type abbreviation."""
    
    document_type: str = Field(
        ...,
        description="Full document type name (e.g., Credit Opinion, TAX)",
        max_length=100
    )
    
    abbreviation: str = Field(
        ...,
        description="Standard abbreviation (e.g., CO, TAX)",
        max_length=10
    )
    
    is_active: bool = Field(
        default=True,
        description="Whether this abbreviation is active"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Credit Opinion",
                "abbreviation": "CO",
                "is_active": True
            }
        }
    )


class DocumentTypeAbbreviationUpdateRequest(BaseModel):
    """Request schema for updating an existing document type abbreviation."""
    
    document_type: Optional[str] = Field(
        None,
        description="Full document type name (e.g., Credit Opinion, TAX)",
        max_length=100
    )
    
    abbreviation: Optional[str] = Field(
        None,
        description="Standard abbreviation (e.g., CO, TAX)",
        max_length=10
    )
    
    is_active: Optional[bool] = Field(
        None,
        description="Whether this abbreviation is active"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Credit Opinion",
                "abbreviation": "CO",
                "is_active": True
            }
        }
    )


class DocumentTypeAbbreviationResponse(BaseModel):
    """Response schema for document type abbreviation."""
    
    id: UUID
    document_type: str
    abbreviation: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)


class DocumentTypeAbbreviationListResponse(BaseModel):
    """Lightweight response schema for listing document type abbreviations."""
    
    id: UUID
    document_type: str
    abbreviation: str
    is_active: bool
    
    model_config = ConfigDict(from_attributes=True)


class AbbreviationLookupRequest(BaseModel):
    """Request schema for looking up an abbreviation by document type."""
    
    document_type: str = Field(
        ...,
        description="Document type to look up abbreviation for"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Credit Opinion"
            }
        }
    )


class AbbreviationLookupResponse(BaseModel):
    """Response schema for abbreviation lookup."""
    
    document_type: str = Field(
        ...,
        description="The document type that was looked up"
    )
    
    abbreviation: str = Field(
        ...,
        description="The abbreviation for the document type"
    )
    
    found: bool = Field(
        ...,
        description="Whether the abbreviation was found in the database"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "document_type": "Credit Opinion",
                "abbreviation": "CO",
                "found": True
            }
        }
    )


class CacheStatsResponse(BaseModel):
    """Response schema for cache statistics."""
    
    hits: int = Field(
        ...,
        description="Number of cache hits",
        json_schema_extra={"example": 150}
    )
    
    misses: int = Field(
        ...,
        description="Number of cache misses",
        json_schema_extra={"example": 25}
    )
    
    hit_rate: float = Field(
        ...,
        description="Cache hit rate as a percentage",
        json_schema_extra={"example": 0.8571}
    )
    
    evictions: int = Field(
        ...,
        description="Number of cache evictions",
        json_schema_extra={"example": 5}
    )
    
    expirations: int = Field(
        ...,
        description="Number of cache expirations",
        json_schema_extra={"example": 10}
    )
    
    invalidations: int = Field(
        ...,
        description="Number of cache invalidations",
        json_schema_extra={"example": 3}
    )
    
    errors: int = Field(
        ...,
        description="Number of cache errors",
        json_schema_extra={"example": 0}
    )
    
    size: int = Field(
        ...,
        description="Current cache size",
        json_schema_extra={"example": 75}
    )
    
    max_size: int = Field(
        ...,
        description="Maximum cache size",
        json_schema_extra={"example": 1000}
    )
    
    ttl_seconds: int = Field(
        ...,
        description="Cache TTL in seconds",
        json_schema_extra={"example": 3600}
    )
    
    enabled: bool = Field(
        ...,
        description="Whether caching is enabled",
        json_schema_extra={"example": True}
    )
    
    model_config = ConfigDict(from_attributes=True)


class CacheInvalidationRequest(BaseModel):
    """Request schema for cache invalidation."""
    
    document_type: Optional[str] = Field(
        None,
        description="Specific document type to invalidate. If not provided, invalidates entire cache."
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Invalidate entire cache",
                    "value": {}
                },
                {
                    "summary": "Invalidate specific document type",
                    "value": {
                        "document_type": "Credit Opinion"
                    }
                }
            ]
        }
    )


class CacheInvalidationResponse(BaseModel):
    """Response schema for cache invalidation."""
    
    invalidated_count: int = Field(
        ...,
        description="Number of cache entries invalidated"
    )
    
    message: str = Field(
        ...,
        description="Description of what was invalidated"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "invalidated_count": 5,
                "message": "Invalidated 5 cache entries"
            }
        }
    )
