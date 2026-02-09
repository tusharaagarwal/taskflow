from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional

from app.db.database import get_db
from app.schemas.abbreviation import (
    DocumentTypeAbbreviationCreateRequest,
    DocumentTypeAbbreviationUpdateRequest,
    DocumentTypeAbbreviationResponse,
    DocumentTypeAbbreviationListResponse,
    AbbreviationLookupRequest,
    AbbreviationLookupResponse,
    CacheStatsResponse,
    CacheInvalidationRequest,
    CacheInvalidationResponse
)
from app.services.abbreviation_service import AbbreviationService, get_abbreviation_service
from app.models.abbreviation import DocumentTypeAbbreviation

router = APIRouter(prefix="/abbreviation", tags=["Abbreviation"])


@router.get("/", response_model=List[DocumentTypeAbbreviationListResponse])
async def list_abbreviations(
    active_only: bool = Query(default=True, description="Filter to active abbreviations only"),
    db: AsyncSession = Depends(get_db)
):
    """List all document type abbreviations."""
    try:
        service = get_abbreviation_service()
        abbreviations = await service.get_all_abbreviations(db, active_only=active_only)
        return abbreviations
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch abbreviations: {str(e)}"
        )


@router.post("/", response_model=DocumentTypeAbbreviationResponse, status_code=status.HTTP_201_CREATED)
async def create_abbreviation(
    create_data: DocumentTypeAbbreviationCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new document type abbreviation."""
    try:
        # Check if abbreviation already exists
        existing = await db.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type == create_data.document_type
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Abbreviation for document type '{create_data.document_type}' already exists"
            )
        
        # Create new abbreviation
        abbreviation = DocumentTypeAbbreviation(**create_data.model_dump())
        db.add(abbreviation)
        await db.commit()
        await db.refresh(abbreviation)
        
        # Invalidate cache
        service = get_abbreviation_service()
        service.invalidate_cache()
        
        return abbreviation
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create abbreviation: {str(e)}"
        )


@router.get("/{document_type}", response_model=DocumentTypeAbbreviationResponse)
async def get_abbreviation_by_document_type(
    document_type: str,
    db: AsyncSession = Depends(get_db)
):
    """Get abbreviation by document type."""
    try:
        result = await db.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type == document_type
            )
        )
        abbreviation = result.scalar_one_or_none()
        
        if not abbreviation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Abbreviation for document type '{document_type}' not found"
            )
        
        return abbreviation
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch abbreviation: {str(e)}"
        )


@router.put("/{document_type}", response_model=DocumentTypeAbbreviationResponse)
async def update_abbreviation(
    document_type: str,
    update_data: DocumentTypeAbbreviationUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Update an existing document type abbreviation."""
    try:
        # Get existing abbreviation
        result = await db.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type == document_type
            )
        )
        abbreviation = result.scalar_one_or_none()
        
        if not abbreviation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Abbreviation for document type '{document_type}' not found"
            )
        
        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        for field, value in update_dict.items():
            setattr(abbreviation, field, value)
        
        await db.commit()
        await db.refresh(abbreviation)
        
        # Invalidate cache
        service = get_abbreviation_service()
        service.invalidate_cache(document_type=document_type)
        
        return abbreviation
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update abbreviation: {str(e)}"
        )


@router.delete("/{document_type}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_abbreviation(
    document_type: str,
    db: AsyncSession = Depends(get_db)
):
    """Delete a document type abbreviation."""
    try:
        # Get existing abbreviation
        result = await db.execute(
            select(DocumentTypeAbbreviation).where(
                DocumentTypeAbbreviation.document_type == document_type
            )
        )
        abbreviation = result.scalar_one_or_none()
        
        if not abbreviation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Abbreviation for document type '{document_type}' not found"
            )
        
        await db.delete(abbreviation)
        await db.commit()
        
        # Invalidate cache
        service = get_abbreviation_service()
        service.invalidate_cache(document_type=document_type)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete abbreviation: {str(e)}"
        )


@router.post("/lookup", response_model=AbbreviationLookupResponse)
async def lookup_abbreviation(
    lookup_data: AbbreviationLookupRequest,
    db: AsyncSession = Depends(get_db)
):
    """Look up abbreviation by document type."""
    try:
        service = get_abbreviation_service()
        
        try:
            abbreviation = await service.get_abbreviation(db, lookup_data.document_type)
            return AbbreviationLookupResponse(
                document_type=lookup_data.document_type,
                abbreviation=abbreviation,
                found=True
            )
        except ValueError:
            # Not found, return default response
            return AbbreviationLookupResponse(
                document_type=lookup_data.document_type,
                abbreviation="",
                found=False
            )
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to lookup abbreviation: {str(e)}"
        )


@router.get("/cache/stats", response_model=CacheStatsResponse)
async def get_cache_stats():
    """Get abbreviation cache statistics."""
    try:
        service = get_abbreviation_service()
        stats = service.get_cache_stats()
        return CacheStatsResponse(**stats)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache stats: {str(e)}"
        )


@router.post("/cache/invalidate", response_model=CacheInvalidationResponse)
async def invalidate_cache(
    invalidation_data: CacheInvalidationRequest = CacheInvalidationRequest()
):
    """Invalidate abbreviation cache."""
    try:
        service = get_abbreviation_service()
        count = service.invalidate_cache(document_type=invalidation_data.document_type)
        
        if invalidation_data.document_type:
            message = f"Invalidated cache for document type: {invalidation_data.document_type}"
        else:
            message = f"Invalidated entire cache ({count} entries)"
        
        return CacheInvalidationResponse(
            invalidated_count=count,
            message=message
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to invalidate cache: {str(e)}"
        )


@router.post("/cache/cleanup", response_model=CacheInvalidationResponse)
async def cleanup_cache():
    """Clean up expired cache entries."""
    try:
        service = get_abbreviation_service()
        count = service.cleanup_expired_cache()
        
        return CacheInvalidationResponse(
            invalidated_count=count,
            message=f"Cleaned up {count} expired cache entries"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cleanup cache: {str(e)}"
        )
