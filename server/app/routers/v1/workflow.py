from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.workflow_schemas import (
    WorkflowDetail,
    WorkflowListItem,
    WorkflowListResponse,
    WorkflowUpdateRequest,
)
from app.services.workflow_service import WorkflowService

router = APIRouter(prefix="/workflows", tags=["Workflows"])


@router.get("/", response_model=WorkflowListResponse)
async def list_workflows(
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db),
):
    """List workflows with optional is_active filter. Excludes soft-deleted."""
    workflows = await WorkflowService.get_workflows(db, is_active=is_active)
    total = await WorkflowService.get_workflow_count(db, is_active=is_active)
    items = [
        WorkflowListItem(
            workflow_id=w.workflow_id,
            name=WorkflowService.resolve_workflow_name(w),
            is_active=w.is_active,
            created_at=w.created_at,
            updated_at=w.updated_at,
        )
        for w in workflows
    ]
    return WorkflowListResponse(items=items, total=total)


@router.get("/{workflow_id}", response_model=WorkflowDetail)
async def get_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get workflow by ID. Returns 404 if not found or soft-deleted."""
    workflow = await WorkflowService.get_workflow_by_id(db, workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with workflow_id '{workflow_id}' not found",
        )
    workflow_json = WorkflowService.parse_workflow_json_raw(workflow.workflow_json)
    return WorkflowDetail(
        workflow_id=workflow.workflow_id,
        name=WorkflowService.resolve_workflow_name(workflow),
        is_active=workflow.is_active,
        workflow_json=workflow_json,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.patch("/{workflow_id}", response_model=WorkflowDetail)
async def update_workflow(
    workflow_id: int,
    body: WorkflowUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Update workflow by ID. Only provided fields are updated. Returns 404 if not found or soft-deleted."""
    workflow = await WorkflowService.update_workflow(db, workflow_id, body)
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with workflow_id '{workflow_id}' not found",
        )
    workflow_json = WorkflowService.parse_workflow_json_raw(workflow.workflow_json)
    return WorkflowDetail(
        workflow_id=workflow.workflow_id,
        name=WorkflowService.resolve_workflow_name(workflow),
        is_active=workflow.is_active,
        workflow_json=workflow_json,
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete workflow by ID. Sets deleted_at. Returns 404 if not found or already deleted."""
    workflow = await WorkflowService.soft_delete_workflow(db, workflow_id)
    if workflow is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workflow with workflow_id '{workflow_id}' not found",
        )
