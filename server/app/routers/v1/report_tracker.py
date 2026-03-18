from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.db.database import get_db
from app.schemas.report_tracker import (
    ReportTrackerStatusResponse,
    ReportTrackerStatusLiteResponse,
    ReportCurrentStageResponse,
    ReportTrackerResponse, 
    ReportTrackerCreateRequest, 
    ReportTrackerListResponse,
    ReportTrackerUpdateRequest,
    AssignUserToStepRequest,
    AssignUserToStepV2Request,
    ReportTrackerWorkflowResponse
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
    """
    Create a new report tracker record.

    After creating the tracker, notifies the Content Assembler to start
    creating the first draft of the report.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        logger.info("Report tracker create: starting (Step 1 create)")
        # Step 1: Create the report tracker in database
        tracker = await ReportTrackerService.create(db, create_data)
        logger.info("Report tracker create: Step 1 done, report_id=%s", tracker.report_id)

        # Step 2: Notify Content Assembler to start drafting
        from app.services.aws.messaging_service import get_messaging_service
        from app.config.config import settings

        logger.info(
            "Report tracker create: messaging_enabled=%s (Step 2 notify assembler)",
            settings.messaging_enabled,
        )
        if settings.messaging_enabled:
            try:
                logger.info("Report tracker create: calling get_messaging_service().notify_assembler_to_start")
                messaging_service = get_messaging_service()
                messaging_result = messaging_service.notify_assembler_to_start(
                    report_id=tracker.report_id,
                    workflow_id=str(tracker.id),
                    cpm_id=tracker.cpm_id,
                    pr_id=tracker.pr_id,
                    transaction_id=tracker.transaction_id,
                    action_code=tracker.action_code,
                )
                logger.info(
                    "Report tracker create: Notified Content Assembler for report_id: %s - Result: %s",
                    tracker.report_id,
                    messaging_result
                )
            except Exception as messaging_error:
                logger.error(
                    "Report tracker create: Failed to notify Content Assembler for report_id: %s - Error: %s",
                    tracker.report_id,
                    str(messaging_error),
                    exc_info=True,
                )
        else:
            logger.info(
                "Report tracker create: skipping notify assembler (messaging_enabled=False)"
            )

        # Step 3: Return the response
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            transaction_id=tracker.transaction_id,
            pr_id=tracker.pr_id,
            cpm_id=tracker.cpm_id,
            action_code=tracker.action_code,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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
    Update report tracker workflow state and/or step app_data.
    
    This endpoint supports three use cases:
    
    **1. Workflow Action Only** - Move workflow forward or backward:
    ```json
    {"action": "accept"}
    ```
    
    **2. Update App_Data Only** - Update current step's app_data without changing workflow state:
    ```json
    {"app_data": {"assignee": [{"user_id": "123", "name": "John"}], "custom_field": "value"}}
    ```
    
    **3. Update Specific Step by Instance ID** - Target any step using its instance_id:
    ```json
    {"instance_id": "550e8400-e29b-41d4-a716-446655440000", "app_data": {"reviewed": true}}
    ```
    
    **4. Combined Action + App_Data** - Perform action AND update app_data:
    ```json
    {"action": "submit", "app_data": {"notes": "Ready for review"}}
    ```
    
    **Actions:**
    - Forward (move to success_goto): accept, submit, approve
    - Backward (move to fail_goto): reject, push_back, pull_back
    - Special (TBD): publish, raise_exemption
    
    **Validation:**
    - At least one of 'action' or 'app_data' must be provided
    - If instance_id provided, step must exist in progress tracker

    **Assignee in status_lite:** To show assignee on the in-progress step, use app_data only (no action) for the current step, or instance_id + app_data (no action) for any step; status_lite will reflect it when that step is current.
    """
    try:
        tracker = await ReportTrackerService.update(db, report_id, update_data)
        
        if not tracker:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report tracker with report_id '{report_id}' not found"
            )

        # Notify consumer applications (orchestrator-to-workspace) on any workflow update
        import logging
        from app.services.aws.messaging_service import get_messaging_service
        from app.config.config import settings

        update_logger = logging.getLogger(__name__)
        update_logger.info(
            "Report tracker update: report_id=%s, messaging_enabled=%s",
            report_id,
            settings.messaging_enabled,
        )
        if settings.messaging_enabled:
            try:
                additional = {}
                if update_data.action is not None:
                    additional["action"] = update_data.action
                get_messaging_service().notify_consumers(
                    report_id=tracker.report_id,
                    event_type="report_tracker_updated",
                    pr_id=tracker.pr_id,
                    transaction_id=tracker.transaction_id,
                    status="completed",
                    additional_data=additional if additional else None,
                )
                update_logger.info(
                    "Report tracker update: Notified consumers - report_id: %s, action: %s",
                    tracker.report_id,
                    update_data.action,
                )
            except Exception as notify_err:
                update_logger.warning(
                    "Report tracker update: Failed to notify consumers for report_id %s: %s: %s",
                    tracker.report_id,
                    type(notify_err).__name__,
                    str(notify_err),
                    exc_info=True,
                )
        else:
            update_logger.info("Report tracker update: skipping notify consumers (messaging_enabled=False)")

        # Manually construct response to debug validation error
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            transaction_id=tracker.transaction_id,
            pr_id=tracker.pr_id,
            cpm_id=tracker.cpm_id,
            action_code=tracker.action_code,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
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


@router.get("/{report_id}/status/exclude-assembler", response_model=ReportTrackerStatusResponse)
async def get_status_exclude_first_assembler_step(
    report_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get report status by report_id with progress_tracker starting from the first human step,
    excluding the leading agent assembler step. Same response shape as GET /{report_id}/status.
    """
    status_data = await ReportTrackerService.get_status_exclude_first_assembler_step(db, report_id)
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    return status_data


@router.get("/{report_id}/status_lite", response_model=ReportTrackerStatusLiteResponse)
async def get_report_status_lite(
    report_id: str,
    exclude_assembler: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """
    Get report status in lite format: report_id and stages array only.

    **Response:** report_id (string), stages (array of stage objects with snake_case fields):
    id (1-based int), title, assignee, role, due_date, start_date, completed_date, status.
    Dates in MM/DD/YYYY HH:MM:SS AM/PM; start_date empty string if not started;
    completed_date empty string if not completed. status is the same as GET /status (e.g. yet_to_start, in_progress, completed, retry, skipped, rejected), or empty string if missing.

    **Query Parameters:**
    - exclude_assembler (bool, default: false): If true, stages start from the first human step,
      excluding the leading agent assembler step.
    """
    status_data = await ReportTrackerService.get_status_lite(db, report_id, exclude_assembler=exclude_assembler)
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    return status_data


@router.get("/{report_id}/current-stage", response_model=ReportCurrentStageResponse)
async def get_report_current_stage(
    report_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get current stage summary for workspace consumption.

    Returns current step name and full ordered workflow steps with
    resolved role and actions available.
    """
    stage_data = await ReportTrackerService.get_current_stage_summary(db, report_id)
    if not stage_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    return stage_data


@router.get("/{report_id}/status", response_model=ReportTrackerStatusResponse)
async def get_report_status(
    report_id: str,
    include_audit: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """
    Get report status by report_id.
    Returns progress_tracker with existing and future steps following the happy path.
    
    **Query Parameters:**
    - `include_audit` (bool, default: true): Controls whether audit data 
      (started_at, completed_at) is included in the response.
    
    **Example requests:**
    - `GET /report-tracker/PR-123/status` - Full response with audit data
    - `GET /report-tracker/PR-123/status?include_audit=false` - Response without audit fields
    """
    status_data = await ReportTrackerService.get_status(db, report_id, include_audit=include_audit)
    
    if not status_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    
    return status_data


@router.get("/{report_id}/workflow", response_model=ReportTrackerWorkflowResponse)
async def get_report_workflow(
    report_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get workflow definition by report_id.
    
    Returns the complete workflow JSON definition including all steps and their transitions.
    This is the original workflow template associated with the report tracker.
    """
    tracker = await ReportTrackerService.get_by_report_id(db, report_id)
    
    if not tracker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Report tracker with report_id '{report_id}' not found"
        )
    
    return ReportTrackerWorkflowResponse(
        report_id=tracker.report_id,
        workflow_json=tracker.workflow_json
    )


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
        transaction_id=tracker.transaction_id,
        pr_id=tracker.pr_id,
        cpm_id=tracker.cpm_id,
        action_code=tracker.action_code,
        workflow_json=tracker.workflow_json,
        workflow_steps_json=tracker.workflow_steps_json,
        created_at=tracker.created_at,
        updated_at=tracker.updated_at
    )


@router.post("/assign-user", response_model=ReportTrackerResponse, deprecated=True)
async def assign_user_to_step(
    assign_data: AssignUserToStepRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    **Deprecated** — use POST /assign-user-v2 instead.

    Assign a user to a particular step in the workflow of a particular report.

    Finds the step in progress_tracker where:
    - status is "in_progress"
    - stage_name matches
    - step_name matches

    Then adds an assignee object to that step's app_data.assignee array.
    """
    response.headers["Deprecation"] = "assign-user-v1"
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
        
        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            transaction_id=tracker.transaction_id,
            pr_id=tracker.pr_id,
            cpm_id=tracker.cpm_id,
            action_code=tracker.action_code,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e.detail)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/assign-user-v2", response_model=ReportTrackerResponse)
async def assign_user_to_step_v2(
    assign_data: AssignUserToStepV2Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Assign a user to a workflow step identified by instance_id (v2).

    Deactivates all currently active assignees on the target step,
    then appends a new assignee record with full lifecycle timestamps.
    Works on steps in any status (yet_to_start, in_progress, completed, retry).
    """
    try:
        tracker = await ReportTrackerService.assign_user_to_step_v2(
            db=db,
            report_id=assign_data.report_id,
            instance_id=assign_data.instance_id,
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

        return ReportTrackerResponse(
            id=tracker.id,
            report_id=tracker.report_id,
            transaction_id=tracker.transaction_id,
            pr_id=tracker.pr_id,
            cpm_id=tracker.cpm_id,
            action_code=tracker.action_code,
            workflow_json=tracker.workflow_json,
            workflow_steps_json=tracker.workflow_steps_json,
            created_at=tracker.created_at,
            updated_at=tracker.updated_at
        )
    except UnprocessableEntityException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(e.detail)
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
