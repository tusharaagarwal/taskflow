import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.report_tracker import ReportTracker
from app.models.content_product import ContentProduct
from app.schemas.report_tracker import ReportTrackerCreateRequest
from app.constants import WorkflowActionType

logger = logging.getLogger(__name__)


class ReportTrackerService:
    """
    Service for managing report tracker workflows.
    
    Handles creation, retrieval, and progression of report workflows through various stages.
    Each workflow consists of steps that can be accepted (move forward) or rejected (move backward).
    """
    
    def __init__(self):
        pass

    @staticmethod
    async def create(db: AsyncSession, create_data: ReportTrackerCreateRequest) -> ReportTracker:
        """
        Create a new report tracker for a given report and content product.
        
        Args:
            db: Async database session
            create_data: Request data containing report_id and content_product_name
            
        Returns:
            Newly created ReportTracker instance with initialized workflow
            
        Raises:
            UnprocessableEntityException: If report_id already exists
            ValueError: If content product is not found or has no workflow
        """
        from app.exceptions import UnprocessableEntityException
        
        # Check if a report tracker with the same report_id already exists
        existing_tracker = await ReportTrackerService.get_by_report_id(db, create_data.report_id)
        if existing_tracker:
            raise UnprocessableEntityException(
                detail=f"Report tracker with report_id '{create_data.report_id}' already exists"
            )
        
        # Get CPM record from mock or real API
        from app.services.cpm_client_service import CPMClientService
        
        print(f"[DEBUG] Fetching CPM record for lob={create_data.lob}, sub_lob={create_data.sub_lob}, cp_name={create_data.content_product_name}")
        cpm_record = await CPMClientService.get_cpm_by_filters(
            lob=create_data.lob,
            sub_lob=create_data.sub_lob,
            cp_name=create_data.content_product_name
        )
        
        # Extract workflow_id (UUID string) from CPM record
        workflow_id = cpm_record.get("workflow_id")
        if not workflow_id:
            print(f"[ERROR] No workflow_id in CPM record")
            raise ValueError(f"No workflow_id in CPM record for lob={create_data.lob}, sub_lob={create_data.sub_lob}, cp_name={create_data.content_product_name}")
        
        # Get the workflow JSON using the workflow_id (UUID)
        from app.services.workflow_service import WorkflowService
        print(f"[DEBUG] Getting workflow JSON for workflow_id: {workflow_id}")
        workflow_json = await WorkflowService.get_workflow_json_from_workflow(db, workflow_id)
        
        if not workflow_json:
            print(f"[ERROR] Workflow not found for workflow_id: {workflow_id}")
            raise ValueError(f"Workflow not found for workflow_id '{workflow_id}'")
        
        # Ensure workflow_json is a dictionary
        if isinstance(workflow_json, str):
            try:
                workflow_json = json.loads(workflow_json)
            except json.JSONDecodeError:
                print(f"[ERROR] Invalid workflow JSON format: {workflow_json}")
                workflow_json = {}
        
        # Create the tracker with default empty workflow_steps_json
        tracker = ReportTracker(
            report_id=create_data.report_id,
            workflow_json=workflow_json if isinstance(workflow_json, dict) else {},
            workflow_steps_json=create_data.create_workflow_steps_json(workflow_json)
        )
        
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)
        
        return tracker

    @staticmethod
    async def get_by_report_id(db: AsyncSession, report_id: str) -> Optional[ReportTracker]:
        """
        Retrieve a report tracker by its report ID.
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            
        Returns:
            ReportTracker instance if found, None otherwise
        """
        result = await db.execute(
            select(ReportTracker).where(ReportTracker.report_id == report_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _find_step_in_workflow_json(workflow_json: dict, step_id: str) -> Optional[dict]:
        """
        Locate a step definition in the workflow JSON by its step_id.
        
        Args:
            workflow_json: Complete workflow definition
            step_id: Identifier of the step to find
            
        Returns:
            Step definition dictionary if found, None otherwise
        """
        if not workflow_json or "steps" not in workflow_json:
            return None
        
        for step in workflow_json["steps"]:
            if step.get("step_id") == step_id:
                return step
        return None

    @staticmethod
    def _is_auto_complete_stage(stage_name: str) -> bool:
        """
        Check if a stage should be automatically completed upon activation.
        
        Args:
            stage_name: Name of the workflow stage
            
        Returns:
            True if stage auto-completes, False otherwise
        """
        auto_complete_stages = ["Published"]
        return stage_name in auto_complete_stages

    @staticmethod
    def _are_all_steps_completed(steps: list, workflow_json: dict) -> bool:
        """
        Determine if all workflow steps have been completed.
        
        Checks if the last step is completed and has no further transitions.
        
        Args:
            steps: List of step instances in progress tracker
            workflow_json: Complete workflow definition
            
        Returns:
            True if workflow is fully complete, False otherwise
        """
        if not steps:
            return False
        
        for step in steps:
            if step.get("status") in ["in_progress", "retry"]:
                return False
        
        last_step = steps[-1]
        if last_step.get("status") != "completed":
            return False
        
        step_id = last_step.get("step_id")
        if not step_id:
            return False
            
        step_json = ReportTrackerService._find_step_in_workflow_json(workflow_json, step_id)
        if not step_json:
            return False
            
        transitions = step_json.get("transitions", {})
        success_goto = transitions.get("success_goto")
        
        return not success_goto or success_goto == "NA"

    @staticmethod
    def _resolve_transition_path(
        transition_value: Any,
        path: Optional[str] = None,
        transition_type: str = "success_goto"
    ) -> str:
        """
        Resolve the target step_id from a transition value that may be a string or nested dict.
        
        Supports two transition formats:
        1. Simple string: "next_step_id"
        2. Nested dict with conditional paths:
           {
             "default": "standard_next_step",
             "exemption": {
               "std": "publish",
               "errc": "errs_review"
             },
             "fast_track": "priority_step"
           }
        
        Args:
            transition_value: The success_goto or fail_goto value from transitions
            path: Optional path string (e.g., "exemption/errc") to navigate nested dict.
                  Path segments are separated by '/'.
            transition_type: Either "success_goto" or "fail_goto" for error messages
            
        Returns:
            The resolved step_id string
            
        Raises:
            UnprocessableEntityException: If path is provided but not found in nested structure
        """
        from app.exceptions import UnprocessableEntityException
        
        # If transition_value is a simple string, return it directly
        if isinstance(transition_value, str):
            return transition_value
        
        # If transition_value is not a dict, return "NA"
        if not isinstance(transition_value, dict):
            return "NA"
        
        # If no path provided, use "default" key
        if not path:
            default_value = transition_value.get("default")
            if default_value is None:
                raise UnprocessableEntityException(
                    detail=f"No path provided and no 'default' key found in {transition_type}"
                )
            # Recursively resolve in case default is also nested
            return ReportTrackerService._resolve_transition_path(
                default_value, None, transition_type
            )
        
        def _path_options(value: Any) -> List[str]:
            if not isinstance(value, dict):
                return []
            paths: List[str] = []
            for key, child in value.items():
                if key == "default":
                    continue
                if isinstance(child, dict):
                    for nested in _path_options(child):
                        paths.append(f"{key}/{nested}")
                elif isinstance(child, str):
                    paths.append(key)
            return paths

        def _invalid_path_message(path_value: str, options: List[str]) -> str:
            if options:
                return f"invalid path:{path_value}. available options:{', '.join(options)}"
            return f"invalid path:{path_value}. available options:"

        # Parse the path (e.g., "exemption/errc/approved" -> ["exemption", "errc", "approved"])
        path_segments = path.split("/")
        
        # Navigate through the nested structure
        current_value = transition_value
        traversed_path = []
        
        for segment in path_segments:
            traversed_path.append(segment)
            
            if not isinstance(current_value, dict):
                raise UnprocessableEntityException(
                    detail=_invalid_path_message(path, _path_options(transition_value))
                )
            
            if segment not in current_value:
                raise UnprocessableEntityException(
                    detail=_invalid_path_message(path, _path_options(transition_value))
                )
            
            current_value = current_value[segment]
        
        # The final value should be a string (step_id)
        if isinstance(current_value, str):
            return current_value
        
        # If final value is a dict, try to get "default" from it
        if isinstance(current_value, dict):
            if "default" in current_value:
                return ReportTrackerService._resolve_transition_path(
                    current_value["default"], None, transition_type
                )
            raise UnprocessableEntityException(
                detail=_invalid_path_message(path, _path_options(transition_value))
            )
        
        raise UnprocessableEntityException(
            detail=_invalid_path_message(path, _path_options(transition_value))
        )

    @staticmethod
    def _get_default_transition(transition_value: Any) -> Optional[str]:
        """
        Get the default transition target for building happy path.
        
        For simple string values, returns the string.
        For nested dict values, returns the 'default' key value.
        
        Args:
            transition_value: The success_goto or fail_goto value
            
        Returns:
            The default step_id string, or None if not found
        """
        if isinstance(transition_value, str):
            return transition_value
        
        if isinstance(transition_value, dict):
            default_value = transition_value.get("default")
            if default_value:
                return ReportTrackerService._get_default_transition(default_value)
        
        return None

    @staticmethod
    def _create_step_object(step_json: dict, status: Optional[str] = None) -> dict:
        """
        Create a new step instance from a step definition.
        
        Each instance receives a unique UUID to distinguish it from other instances
        of the same step that may occur after rejections.
        
        Args:
            step_json: Step definition from workflow JSON
            status: Optional status override; defaults to 'in_progress' or 'completed' for auto-complete stages
            
        Returns:
            Step instance dictionary with unique instance_id
        """
        current_time = datetime.now(timezone.utc).isoformat()
        stage_name = step_json.get("stage_name", "")
        is_auto_complete = ReportTrackerService._is_auto_complete_stage(stage_name)
        
        if status is None:
            default_status = "completed" if is_auto_complete else "in_progress"
        else:
            default_status = status
        
        return {
            "instance_id": str(uuid.uuid4()),
            "step_id": step_json.get("step_id"),
            "step_name": step_json.get("step_name"),
            "stage_name": stage_name,
            "actor": step_json.get("actor", {}),
            "is_optional": step_json.get("is_optional", False),
            "sla": step_json.get("sla", {}),
            "action_available": step_json.get("action_available", []),
            "app_data": {
                "assignee": [],
                "personas": step_json.get("personas", [])
            },
            "started_at": current_time if default_status != "yet_to_start" else None,
            "completed_at": current_time if is_auto_complete and default_status == "completed" else None,
            "status": default_status
        }

    @staticmethod
    def _build_happy_path(workflow_json: dict, start_step_id: str, current_time: str) -> list:
        """
        Build happy path steps starting from a given step_id.
        
        Args:
            workflow_json: The workflow JSON
            start_step_id: Step ID to start building from
            current_time: ISO timestamp string
            
        Returns:
            List of step objects following success_goto transitions
        """
        if not workflow_json or "steps" not in workflow_json:
            return []
        
        # Create step_id -> step_json map
        step_map = {}
        for step in workflow_json["steps"]:
            step_id = step.get("step_id")
            if step_id:
                step_map[step_id] = step
        
        happy_path = []
        visited_steps = set()
        current_step_id = start_step_id
        
        while current_step_id and current_step_id != "NA" and current_step_id not in visited_steps:
            visited_steps.add(current_step_id)
            step_json = step_map.get(current_step_id)
            
            if not step_json:
                break
            
            stage_name = step_json.get("stage_name", "")
            is_auto_complete = ReportTrackerService._is_auto_complete_stage(stage_name)
            
            step_obj = {
                "instance_id": str(uuid.uuid4()),
                "step_id": step_json.get("step_id"),
                "step_name": step_json.get("step_name"),
                "stage_name": stage_name,
                "actor": step_json.get("actor", {}),
                "is_optional": step_json.get("is_optional", False),
                "sla": step_json.get("sla", {}),
                "action_available": step_json.get("action_available", []),
                "app_data": {
                    "assignee": [],
                    "personas": step_json.get("personas", [])
                },
                "started_at": None,
                "completed_at": None,
                "status": "yet_to_start"
            }
            
            if len(happy_path) == 0:
                step_obj["status"] = "in_progress"
                step_obj["started_at"] = current_time
                if is_auto_complete:
                    step_obj["status"] = "completed"
                    step_obj["completed_at"] = current_time
            else:
                step_obj["status"] = "yet_to_start"
            
            happy_path.append(step_obj)
            
            transitions = step_json.get("transitions", {})
            success_goto_raw = transitions.get("success_goto")
            # Use default transition for happy path building
            current_step_id = ReportTrackerService._get_default_transition(success_goto_raw)
        
        return happy_path

    @staticmethod
    def _accept(
        tracker: ReportTracker,
        steps: list,
        current_step: dict,
        current_step_json: dict,
        workflow_json: dict,
        path: Optional[str] = None
    ) -> None:
        """
        Accept the current step and progress to the next step in the workflow.
        
        Handles three transition scenarios based on resolved success_goto value:
        
        1. "RETRY" keyword: Lightweight retry - keeps same instance, sets status to 'retry'
        2. Self-loop (success_goto == current step_id): Creates NEW instance of the step,
           marks current as 'completed', preserving full audit trail
        3. Different step_id: Normal forward progression to next step
        
        Uses a three-tier lookup strategy to identify the correct step instance:
        1. Match by unique instance_id (most reliable)
        2. Match by object identity (for in-memory consistency)
        3. Reverse search by step_id and status (fallback for edge cases)
        
        Args:
            tracker: ReportTracker instance being updated
            steps: List of step instances in progress tracker
            current_step: The step instance being accepted
            current_step_json: Step definition from workflow JSON
            workflow_json: Complete workflow definition
            path: Optional path for resolving nested transition objects
            
        Raises:
            UnprocessableEntityException: If step cannot be accepted or next step not found
        """
        from app.exceptions import UnprocessableEntityException
        
        current_time = datetime.now(timezone.utc).isoformat()
        current_step_id = current_step.get("step_id")
        current_instance_id = current_step.get("instance_id")
        
        transitions = current_step_json.get("transitions", {})
        success_goto_raw = transitions.get("success_goto")
        
        if not success_goto_raw or success_goto_raw == "NA":
            raise UnprocessableEntityException(
                detail=f"Cannot accept step {current_step_id}: success_goto is NA"
            )
        
        # Resolve the transition path to get the actual step_id
        # This handles both simple string values and nested dict structures
        # The resolved value can be: a step_id, "RETRY", or "NA"
        success_goto = ReportTrackerService._resolve_transition_path(
            success_goto_raw, path, "success_goto"
        )
        
        # =============================================================================
        # RETRY KEYWORD HANDLING (Lightweight Retry - Same Instance)
        # =============================================================================
        # When success_goto resolves to "RETRY", we keep the same step instance
        # and reset its status to "retry". This is useful for event-driven retries
        # where we want the same assignee to continue working on the step.
        # 
        # Example workflow JSON:
        #   "success_goto": {
        #     "default": "next_step",
        #     "validation_result": {
        #       "needs_recheck": "RETRY"
        #     }
        #   }
        # =============================================================================
        if success_goto == "RETRY":
            current_step["status"] = "retry"
            current_step["completed_at"] = None
            return
        
        if not success_goto or success_goto == "NA":
            raise UnprocessableEntityException(
                detail=f"Cannot accept step {current_step_id}: resolved success_goto is NA"
            )
        
        # =============================================================================
        # FIND CURRENT STEP INDEX (Three-tier lookup strategy)
        # =============================================================================
        # We need to find the current step's index in the progress tracker list
        # before we can handle self-loops or forward progression.
        # =============================================================================
        current_step_index = None
        
        # Tier 1: Match by unique instance_id (most reliable)
        if current_instance_id:
            for i, step in enumerate(steps):
                if step.get("instance_id") == current_instance_id:
                    current_step_index = i
                    break
        
        # Tier 2: Object identity (reliable for in-memory operations)
        if current_step_index is None:
            for i, step in enumerate(steps):
                if step is current_step:
                    current_step_index = i
                    break
        
        # Tier 3: Fallback - reverse search by step_id and status
        if current_step_index is None:
            for i in range(len(steps) - 1, -1, -1):
                if (steps[i].get("step_id") == current_step_id and 
                    steps[i].get("status") in ["in_progress", "retry"]):
                    current_step_index = i
                    break
        
        if current_step_index is None:
            raise UnprocessableEntityException(
                detail=f"Current step {current_step_id} not found in progress tracker"
            )
        
        # =============================================================================
        # SELF-LOOP HANDLING (New Instance Creation)
        # =============================================================================
        # When success_goto resolves to the SAME step_id as the current step,
        # we create a NEW instance of the step. This preserves audit history:
        # - The current instance is marked as "completed" with a timestamp
        # - A new instance with a fresh instance_id is inserted at current+1
        # - The new instance starts in "in_progress" status
        # 
        # This differs from "RETRY" which reuses the same instance.
        # Use self-loop when you need full audit trail of each attempt.
        # 
        # Example workflow JSON:
        #   "success_goto": {
        #     "default": "external_review",
        #     "exception": {
        #       "errc": {
        #         "rejected": "l1_approval"  // Points to itself - creates new instance
        #       }
        #     }
        #   }
        # =============================================================================
        if success_goto == current_step_id:
            # Mark current instance as completed (preserves audit trail)
            current_step["status"] = "completed"
            current_step["completed_at"] = current_time
            
            # Create a new instance of the same step with fresh instance_id
            new_step_instance = ReportTrackerService._create_step_object(
                current_step_json, status="in_progress"
            )
            
            # Insert the new instance right after the current step
            steps.insert(current_step_index + 1, new_step_instance)
            return
        
        # =============================================================================
        # NORMAL FORWARD PROGRESSION
        # =============================================================================
        # Mark current step as completed and find the next step in progress tracker
        # =============================================================================
        current_step["status"] = "completed"
        current_step["completed_at"] = current_time
        
        next_step_index = None
        for i in range(current_step_index + 1, len(steps)):
            if steps[i].get("step_id") == success_goto:
                next_step_index = i
                break
        
        if next_step_index is not None:
            next_step = steps[next_step_index]
            next_step["status"] = "in_progress"
            if not next_step.get("started_at"):
                next_step["started_at"] = current_time
            
            while next_step_index < len(steps):
                next_step = steps[next_step_index]
                stage_name = next_step.get("stage_name", "")
                
                if ReportTrackerService._is_auto_complete_stage(stage_name):
                    next_step["status"] = "completed"
                    next_step["completed_at"] = current_time
                    if not next_step.get("started_at"):
                        next_step["started_at"] = current_time
                    
                    next_step_json = ReportTrackerService._find_step_in_workflow_json(
                        workflow_json, next_step.get("step_id")
                    )
                    if not next_step_json:
                        break
                    
                    transitions = next_step_json.get("transitions", {})
                    next_step_id = transitions.get("success_goto")
                    
                    if not next_step_id or next_step_id == "NA":
                        break
                    
                    found = False
                    for i in range(next_step_index + 1, len(steps)):
                        if steps[i].get("step_id") == next_step_id:
                            next_step_index = i
                            found = True
                            break
                    
                    if not found:
                        break
                else:
                    break
        else:
            raise UnprocessableEntityException(
                detail=f"Next step {success_goto} not found in progress tracker"
            )

    @staticmethod
    def _reject(
        tracker: ReportTracker,
        steps: list,
        current_step: dict,
        current_step_json: dict,
        workflow_json: dict,
        path: Optional[str] = None
    ) -> None:
        """
        Reject the current step and handle retry, self-loop, or rollback logic.
        
        Handles three transition scenarios based on resolved fail_goto value:
        
        1. "RETRY" keyword: Lightweight retry - keeps same instance, sets status to 'retry'
        2. Self-loop (fail_goto == current step_id): Creates NEW instance of the step,
           marks current as 'rejected', preserving full audit trail
        3. Different step_id: Normal rejection - marks as 'rejected', removes subsequent
           steps, and rebuilds the path from fail_goto step
        
        NOTE: Self-loop behavior changed from previous implementation where
        fail_goto == current_step_id would set status to 'retry'. To preserve
        the old behavior, use the "RETRY" keyword explicitly in workflow JSON.
        
        Uses the same three-tier lookup strategy as _accept for step identification.
        
        Args:
            tracker: ReportTracker instance being updated
            steps: List of step instances in progress tracker
            current_step: The step instance being rejected
            current_step_json: Step definition from workflow JSON
            workflow_json: Complete workflow definition
            path: Optional path for resolving nested transition objects
            
        Raises:
            UnprocessableEntityException: If step cannot be rejected or fail_goto not found
        """
        from app.exceptions import UnprocessableEntityException
        
        current_time = datetime.now(timezone.utc).isoformat()
        current_step_id = current_step.get("step_id")
        current_instance_id = current_step.get("instance_id")
        
        transitions = current_step_json.get("transitions", {})
        fail_goto_raw = transitions.get("fail_goto")
        
        if not fail_goto_raw or fail_goto_raw == "NA":
            raise UnprocessableEntityException(
                detail=f"Cannot reject step {current_step_id}: fail_goto is NA"
            )
        
        # Resolve the transition path to get the actual step_id
        # This handles both simple string values and nested dict structures
        # The resolved value can be: a step_id, "RETRY", or "NA"
        fail_goto = ReportTrackerService._resolve_transition_path(
            fail_goto_raw, path, "fail_goto"
        )
        
        # =============================================================================
        # RETRY KEYWORD HANDLING (Lightweight Retry - Same Instance)
        # =============================================================================
        # When fail_goto resolves to "RETRY", we keep the same step instance
        # and reset its status to "retry". This is useful for event-driven retries
        # where we want the same assignee to continue working on the step.
        # 
        # Example workflow JSON:
        #   "fail_goto": "RETRY"
        # 
        # Or nested:
        #   "fail_goto": {
        #     "default": "previous_step",
        #     "validation_error": "RETRY"
        #   }
        # =============================================================================
        if fail_goto == "RETRY":
            current_step["status"] = "retry"
            current_step["completed_at"] = None
            return
        
        if not fail_goto or fail_goto == "NA":
            raise UnprocessableEntityException(
                detail=f"Cannot reject step {current_step_id}: resolved fail_goto is NA"
            )
        
        # =============================================================================
        # FIND CURRENT STEP INDEX (Three-tier lookup strategy)
        # =============================================================================
        # We need to find the current step's index in the progress tracker list
        # before we can handle self-loops or normal rejection flow.
        # =============================================================================
        current_step_index = None
        
        # Tier 1: Match by unique instance_id (most reliable)
        if current_instance_id:
            for i, step in enumerate(steps):
                if step.get("instance_id") == current_instance_id:
                    current_step_index = i
                    break
        
        # Tier 2: Object identity (reliable for in-memory operations)
        if current_step_index is None:
            for i, step in enumerate(steps):
                if step is current_step:
                    current_step_index = i
                    break
        
        # Tier 3: Fallback - reverse search by step_id and status
        if current_step_index is None:
            for i in range(len(steps) - 1, -1, -1):
                if (steps[i].get("step_id") == current_step_id and 
                    steps[i].get("status") in ["in_progress", "retry"]):
                    current_step_index = i
                    break
        
        if current_step_index is None:
            raise UnprocessableEntityException(
                detail=f"Current step {current_step_id} not found in progress tracker"
            )
        
        # =============================================================================
        # SELF-LOOP HANDLING (New Instance Creation)
        # =============================================================================
        # When fail_goto resolves to the SAME step_id as the current step,
        # we create a NEW instance of the step. This preserves audit history:
        # - The current instance is marked as "rejected" with a timestamp
        # - A new instance with a fresh instance_id is inserted at current+1
        # - The new instance starts in "in_progress" status
        # 
        # This differs from "RETRY" which reuses the same instance.
        # Use self-loop when you need full audit trail of each rejection/retry.
        # 
        # Example workflow JSON:
        #   "fail_goto": "l1_approval"  // Points to itself - creates new instance
        # 
        # NOTE: This is a BREAKING CHANGE from previous behavior where
        # fail_goto == current_step_id would set status to "retry".
        # To preserve the old behavior, use "RETRY" keyword instead.
        # =============================================================================
        if fail_goto == current_step_id:
            # Mark current instance as rejected (preserves audit trail)
            current_step["status"] = "rejected"
            current_step["completed_at"] = current_time
            
            # Create a new instance of the same step with fresh instance_id
            new_step_instance = ReportTrackerService._create_step_object(
                current_step_json, status="in_progress"
            )
            
            # Insert the new instance right after the current step
            steps.insert(current_step_index + 1, new_step_instance)
            return
        
        # =============================================================================
        # NORMAL REJECTION FLOW (Go to different step)
        # =============================================================================
        # Mark current step as rejected and rebuild path from fail_goto step
        # =============================================================================
        current_step["status"] = "rejected"
        current_step["completed_at"] = current_time
        
        # Remove all steps after the current step
        steps[:] = steps[:current_step_index + 1]
        
        # Find the fail_goto step definition in workflow JSON
        fail_step_json = ReportTrackerService._find_step_in_workflow_json(
            workflow_json, fail_goto
        )
        
        if not fail_step_json:
            raise UnprocessableEntityException(
                detail=f"Step JSON not found for fail_goto step {fail_goto}"
            )
        
        # Rebuild the happy path starting from fail_goto step
        happy_path = ReportTrackerService._build_happy_path(
            workflow_json, fail_goto, current_time
        )
        
        # Append the new path to progress tracker
        steps.extend(happy_path)

    @staticmethod
    async def update(db: AsyncSession, report_id: str, update_data) -> Optional[ReportTracker]:
        """
        Update a report tracker with workflow action.
        
        Supports 8 action types:
        - Forward actions (move to success_goto): accept, submit, approve
        - Backward actions (move to fail_goto): reject, push_back, pull_back
        - Special actions (no-op, TBD): publish, raise_exemption
        
        Automatically identifies the current active step and applies the requested action.
        If no step is in progress, activates the first 'yet_to_start' step.
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            update_data: Request containing action (one of 8 supported types)
            
        Returns:
            Updated ReportTracker instance, or None if not found
            
        Raises:
            UnprocessableEntityException: If action cannot be performed or workflow is complete
        """
        from app.exceptions import UnprocessableEntityException
        
        tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if not tracker:
            return None
        
        if not tracker.workflow_steps_json:
            tracker.workflow_steps_json = {"progress_tracker": []}
        
        if "progress_tracker" not in tracker.workflow_steps_json:
            tracker.workflow_steps_json["progress_tracker"] = []
        
        steps = tracker.workflow_steps_json["progress_tracker"]
        workflow_json = tracker.workflow_json or {}
        
        current_step = None
        for step in steps:
            if step.get("status") in ["in_progress", "retry"]:
                current_step = step
                break
        
        if not current_step and WorkflowActionType.is_forward_action(update_data.action):
            if ReportTrackerService._are_all_steps_completed(steps, workflow_json):
                raise UnprocessableEntityException(
                    detail="All workflow steps are already completed. Cannot restart the workflow."
                )
            
            if len(steps) > 0:
                for step in steps:
                    if step.get("status") == "yet_to_start":
                        step["status"] = "in_progress"
                        step["started_at"] = datetime.now(timezone.utc).isoformat()
                        current_step = step
                        break
                
                if not current_step:
                    raise UnprocessableEntityException(
                        detail="No step available to start"
                    )
            else:
                raise UnprocessableEntityException(detail="No workflow steps found")
        
        if not current_step:
            raise UnprocessableEntityException(detail="No step in progress or retry state found")
            
        current_step_id = current_step.get("step_id")
        current_step_json = ReportTrackerService._find_step_in_workflow_json(workflow_json, current_step_id)
        
        if not current_step_json:
            raise UnprocessableEntityException(detail=f"Step JSON not found for step_id {current_step_id}")
        
        # Validate that the requested action is available for this step
        # Get action_available from the workflow JSON definition (source of truth)
        action_available = current_step_json.get("action_available", [])
        
        # If action_available list is defined and not empty, validate the action
        if action_available:
            if update_data.action not in action_available:
                raise UnprocessableEntityException(
                    detail=f"Action '{update_data.action}' is not allowed for step '{current_step_id}'. "
                           f"Available actions: {', '.join(action_available)}"
                )
        # If action_available is empty list, no actions are allowed
        elif action_available == []:
            raise UnprocessableEntityException(
                detail=f"No actions are allowed for step '{current_step_id}'. This step does not accept any actions."
            )
        
        # Get the optional path from update_data (for dynamic transition resolution)
        transition_path = getattr(update_data, "path", None)
        
        # Handle special actions (no-op for now)
        if WorkflowActionType.is_special_action(update_data.action):
            # TBD: Implementation to be discussed
            # For now, these actions don't change workflow state
            # Just return the tracker without modifications
            logger.info(f"Special action '{update_data.action}' executed (no-op) for step '{current_step_id}'")
            return tracker
             
        if WorkflowActionType.is_forward_action(update_data.action):
            ReportTrackerService._accept(
                tracker, steps, current_step, current_step_json, workflow_json, transition_path
            )
        elif WorkflowActionType.is_backward_action(update_data.action):
            ReportTrackerService._reject(
                tracker, steps, current_step, current_step_json, workflow_json, transition_path
            )
        else:
            raise UnprocessableEntityException(detail=f"Invalid action: {update_data.action}")
            
        tracker.workflow_steps_json = {"progress_tracker": steps}
        flag_modified(tracker, "workflow_steps_json")
        await db.commit()
        await db.refresh(tracker)
        return tracker

    @staticmethod
    async def get_all(db: AsyncSession) -> List[Dict[str, Any]]:
        """
        Retrieve all report trackers with basic metadata only.
        
        Returns a lightweight list of all trackers without full workflow data,
        ordered by creation date (newest first).
        
        Args:
            db: Async database session
            
        Returns:
            List of dictionaries containing id, report_id, created_at, updated_at
        """
        result = await db.execute(
            select(ReportTracker).order_by(ReportTracker.created_at.desc())
        )
        trackers = result.scalars().all()
        
        return [
            {
                "id": tracker.id,
                "report_id": tracker.report_id,
                "created_at": tracker.created_at,
                "updated_at": tracker.updated_at
            }
            for tracker in trackers
        ]

    @staticmethod
    async def get_status(db: AsyncSession, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the current workflow status for a specific report.
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            
        Returns:
            Dictionary with report_id and progress_tracker, or None if not found
        """
        tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if not tracker:
            return None
        
        progress_tracker = tracker.workflow_steps_json.get("progress_tracker", []) if tracker.workflow_steps_json else []
        
        return {
            "report_id": tracker.report_id,
            "progress_tracker": progress_tracker
        }

    @staticmethod
    async def assign_user_to_step(
        db: AsyncSession,
        report_id: str,
        stage_name: str,
        step_name: str,
        user_id: str,
        user_name: str,
        user_email: str,
        role: Optional[str] = None
    ) -> Optional[ReportTracker]:
        """
        Assign a user to a specific workflow step that is currently in progress.
        
        Adds assignee information to the step's metadata. Multiple users can be
        assigned to the same step by calling this method multiple times.
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            stage_name: Name of the workflow stage
            step_name: Name of the specific step
            user_id: Unique identifier for the user
            user_name: Display name of the user
            user_email: Email address of the user
            role: Optional role designation for this assignment
            
        Returns:
            Updated ReportTracker instance, or None if tracker not found
            
        Raises:
            UnprocessableEntityException: If no matching in-progress step is found
        """
        from app.exceptions import UnprocessableEntityException
        
        tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if not tracker:
            return None
        
        if not tracker.workflow_steps_json:
            tracker.workflow_steps_json = {"progress_tracker": []}
        
        if "progress_tracker" not in tracker.workflow_steps_json:
            tracker.workflow_steps_json["progress_tracker"] = []
        
        steps = tracker.workflow_steps_json["progress_tracker"]
        
        target_step = None
        for step in steps:
            if (step.get("status") == "in_progress" and
                step.get("stage_name") == stage_name and
                step.get("step_name") == step_name):
                target_step = step
                break
        
        if not target_step:
            raise UnprocessableEntityException(
                detail=f"No step found with status 'in_progress', stage_name '{stage_name}', and step_name '{step_name}' for report_id '{report_id}'"
            )
        
        if "app_data" not in target_step:
            target_step["app_data"] = {}
        
        if not isinstance(target_step["app_data"].get("assignee"), list):
            target_step["app_data"]["assignee"] = []
        
        current_time = datetime.now(timezone.utc).isoformat()
        assignee_object = {
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "role": role,
            "assigned_at": current_time
        }
        
        target_step["app_data"]["assignee"].append(assignee_object)
        
        tracker.workflow_steps_json = {"progress_tracker": steps}
        flag_modified(tracker, "workflow_steps_json")
        await db.commit()
        await db.refresh(tracker)
        
        return tracker

