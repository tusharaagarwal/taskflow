from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.database import get_db
from app.schemas.report_tracker import (
    ReportTrackerStatusResponse, 
    ReportTrackerResponse, 
    ReportTrackerCreateRequest, 
    ReportTrackerListResponse,
    ReportTrackerUpdateRequest,
    AssignUserToStepRequest
)
from app.services.report_tracker_service import ReportTrackerService
from app.exceptions import UnprocessableEntityException

router = APIRouter(prefix="/report-tracker", tags=["Report Tracker"])


@router.get("/", response_model=List[ReportTrackerListResponse])
async def list_report_trackers(
    db: AsyncSession = Depends(get_db)
):
    """List all report tracker records with ID and report_id only."""
    trackers = await ReportTrackerService.get_all(db)
    return trackers


@router.post("/", response_model=ReportTrackerResponse, status_code=status.HTTP_201_CREATED)
async def create_report_tracker(
    create_data: ReportTrackerCreateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Create a new report tracker record."""
    try:
        tracker = await ReportTrackerService.create(db, create_data)
        
        # Manually construct response to debug validation error
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e.detail)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{report_id}", response_model=ReportTrackerResponse)
async def update_report_tracker(
    report_id: str,
    update_data: ReportTrackerUpdateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Update report tracker with workflow action.
    
    Supports 7 action types:
    - Forward actions (move to success_goto): accept, submit, approve
    - Backward actions (move to fail_goto): reject, push_back, pull_back
    
    Forward actions:
    - Mark current step as completed
    - Move to the next step as in_progress
    
    Backward actions:
    - Mark current step as rejected
    - Move back to previous step or create retry based on fail_goto
    """
    try:
        tracker = await ReportTrackerService.update(db, report_id, update_data)
        
        if not tracker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report tracker with report_id '{report_id}' not found"
            )
        
        # Manually construct response to debug validation error
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e.detail)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{report_id}/status", response_model=ReportTrackerStatusResponse)
async def get_report_status(
    report_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get report status by report_id.
    Returns progress_tracker with existing and future steps following the happy path.
    """
    status_data = await ReportTrackerService.get_status(db, report_id)
    
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    
    return status_data


@router.get("/{report_id}", response_model=ReportTrackerResponse)
async def get_report_tracker(
    report_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get report tracker by report_id."""
    tracker = await ReportTrackerService.get_by_report_id(db, report_id)
    
    if not tracker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    
    # Manually construct response to debug validation error
    return ReportTrackerResponse(
        id=tracker.id,
        report_id=tracker.report_id,
        workflow_json=tracker.workflow_json,
        workflow_steps_json=tracker.workflow_steps_json,
        created_at=tracker.created_at,
        updated_at=tracker.updated_at
    )


@router.post("/assign-user", response_model=ReportTrackerResponse)
async def assign_user_to_step(
    assign_data: AssignUserToStepRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Assign a user to a particular step in the workflow of a particular report.
    
    Finds the step in progress_tracker where:
    - status is "in_progress"
    - stage_name matches
    - step_name matches
    
    Then adds an assignee object to that step's app_data.assignee array.
    """
    try:
        tracker = await ReportTrackerService.assign_user_to_step(
            db=db,
            report_id=assign_data.report_id,
            stage_name=assign_data.stage_name,
            step_name=assign_data.step_name,
            user_id=assign_data.user_id,
            user_name=assign_data.user_name,
            user_email=assign_data.user_email,
            role=assign_data.role
        )
        
        if not tracker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report tracker with report_id '{assign_data.report_id}' not found"
            )
        
        # Manually construct response to debug validation error
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e.detail)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
