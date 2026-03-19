import copy
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
from app.utils.security import sanitize_log_input

logger = logging.getLogger(__name__)


class ReportTrackerService:
    """
    Service for managing report tracker workflows.

    Handles creation, retrieval, and progression of report workflows through various stages.
    Each workflow consists of steps that can be accepted (move forward) or rejected (move backward).

    TODO (broader level): Introduce a validator/schema governing how app_data is updated (on PUT, assign-user, merge)
    so that consumer apps maintain a consistent structure (e.g. fixed keys like assignee), avoid conflicting keys,
    and avoid overwriting existing data in an undefined way. Applies to the update path (request validation, merge
    logic when applying app_data to a step), not to getters like _role_for_lite which only read from app_data.
    """
    
    def __init__(self):
        pass

    @staticmethod
    async def create(db: AsyncSession, create_data: ReportTrackerCreateRequest) -> ReportTracker:
        """
        Create a new report tracker for a given report and content product.
        
        Args:
            db: Async database session
            create_data: Request data with transaction_id, pr_id, content_type, document_type
            
        Returns:
            Newly created ReportTracker instance with initialized workflow
            
        Raises:
            UnprocessableEntityException: If report_id already exists
            ValueError: If content product is not found or has no workflow
        """
        from app.exceptions import UnprocessableEntityException
        from sqlalchemy import text
        
        try:
            report_id = await ReportTrackerService._generate_unique_report_id(db, create_data.document_type)
            s_doc_type = sanitize_log_input(create_data.document_type)
            # codeql[py/log-injection]
            logger.info(f"Generated report_id '{sanitize_log_input(report_id)}' for document_type '{s_doc_type}'")
        except Exception as e:
            s_doc_type = sanitize_log_input(create_data.document_type)
            # codeql[py/log-injection]
            logger.error(f"Failed to generate report_id from document_type '{s_doc_type}': {sanitize_log_input(str(e))}")
            raise ValueError(f"Failed to generate report_id: {e}")


        
        # Check if a report tracker with the same report_id already exists
        existing_tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if existing_tracker:
            raise UnprocessableEntityException(
                detail=f"Report tracker with report_id '{report_id}' already exists"
            )
        
        # Get CPM record from mock or real API using content_type as cp_name
        from app.services.cpm_client_service import CPMClientService
        
        s_lob = sanitize_log_input(create_data.lob)
        s_sub_lob = sanitize_log_input(create_data.sub_lob)
        s_content_type = sanitize_log_input(create_data.content_type)
        logger.debug(f"Fetching CPM record for lob={s_lob}, sub_lob={s_sub_lob}, content_type={s_content_type}")
        cpm_record = await CPMClientService.get_cpm_by_filters(
            lob=create_data.lob,
            sub_lob=create_data.sub_lob,
            cp_name=create_data.content_type
        )
        
        # Extract workflow_id and cpm_id from CPM record
        workflow_id = cpm_record.get("workflow_id")
        cpm_id = cpm_record.get("id") or cpm_record.get("cpm_id")  # Try both keys
        
        if not workflow_id:
            logger.error(f"No workflow_id in CPM record")
            raise ValueError(f"No workflow_id in CPM record for lob={create_data.lob}, sub_lob={create_data.sub_lob}, content_type={create_data.content_type}")
        
        # Get the workflow JSON using the workflow_id (UUID)
        from app.services.workflow_service import WorkflowService
        # codeql[py/log-injection]
        logger.debug(f"Getting workflow JSON for workflow_id: {sanitize_log_input(str(workflow_id))}")
        workflow_json = await WorkflowService.get_workflow_json_from_workflow(db, workflow_id)
        
        if not workflow_json:
            # codeql[py/log-injection]
            logger.error(f"Workflow not found for workflow_id: {sanitize_log_input(str(workflow_id))}")
            raise ValueError(f"Workflow not found for workflow_id '{workflow_id}'")
        
        # Ensure workflow_json is a dictionary
        if isinstance(workflow_json, str):
            try:
                workflow_json = json.loads(workflow_json)
            except json.JSONDecodeError:
                # codeql[py/log-injection]
                logger.error(f"Invalid workflow JSON format: {sanitize_log_input(str(workflow_json))}")
                workflow_json = {}
        
        # Create the tracker with all new fields
        tracker = ReportTracker(
            report_id=report_id,
            transaction_id=create_data.transaction_id,
            pr_id=create_data.pr_id,
            cpm_id=cpm_id,
            action_code=create_data.action_code,
            workflow_json=workflow_json if isinstance(workflow_json, dict) else {},
            workflow_steps_json=create_data.create_workflow_steps_json(workflow_json)
        )
        
        db.add(tracker)
        await db.commit()
        await db.refresh(tracker)
        
        return tracker



    @staticmethod
    async def _generate_unique_report_id(db: AsyncSession, document_type: str) -> str:
        """
        Generate a unique report ID using the abbreviation module and database sequence.
        
        Args:
            db: Database session
            document_type: Document type name
            
        Returns:
            Formatted report ID strings (e.g. 'CO_00010001')
        """
        from app.services.abbreviation_service import AbbreviationService
        from sqlalchemy import text

        abbreviation_service = AbbreviationService()
        abbreviation = await abbreviation_service.get_abbreviation(db, document_type)

        # Get next sequence value from PostgreSQL
        # Note: This specific SQL is Postgres-only.
        # For testing with SQLite, this method should be mocked.
        result = await db.execute(text("SELECT nextval('report_id_seq')"))
        sequence_value = result.scalar()

        # Format: {ABBREVIATION}_{SEQUENCE_8D}
        return f"{abbreviation}_{sequence_value:08d}"

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
        success_goto = ReportTrackerService._get_default_transition(transitions.get("success_goto"))
        
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
            "is_optional": step_json.get("is_optional", step_json.get("skippable", False)),
            "sla": step_json.get("sla", {}),
            "action_available": step_json.get("actions_available", step_json.get("action_available", [])),
            "app_data": {
                "assignee": [],
                "personas": step_json.get("persona_required", step_json.get("personas", []))
            },
            "started_at": current_time if default_status != "yet_to_start" else None,
            "completed_at": current_time if is_auto_complete and default_status == "completed" else None,
            "status": default_status
        }

    @staticmethod
    def _clone_step_instance(source_step: dict, status: str = "yet_to_start") -> dict:
        """
        Deep-copy an existing step instance, preserving all accumulated data
        (app_data, assignees, personas, analytics, etc.) while resetting
        identity and temporal fields for a new lifecycle.

        Assignee records keep assigned_at/unassigned_at/status but get their
        started_at and completed_at cleared so that
        _set_assignee_timestamps_on_activation and
        _set_assignee_timestamps_on_completion set fresh values.
        """
        cloned = copy.deepcopy(source_step)
        cloned["instance_id"] = str(uuid.uuid4())
        cloned["status"] = status
        cloned["started_at"] = None
        cloned["completed_at"] = None
        assignees = (cloned.get("app_data") or {}).get("assignee")
        if isinstance(assignees, list):
            for a in assignees:
                if isinstance(a, dict):
                    a["started_at"] = None
                    a["completed_at"] = None
        return cloned

    @staticmethod
    def _find_latest_instance_by_step_id(
        steps: list, step_id: str, up_to_index: int
    ) -> Optional[dict]:
        """
        Search backwards through steps[0..up_to_index] for the most recent
        instance of a given step_id. Returns None if no instance exists.
        """
        for i in range(up_to_index, -1, -1):
            if steps[i].get("step_id") == step_id:
                return steps[i]
        return None

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
                "is_optional": step_json.get("is_optional", step_json.get("skippable", False)),
                "sla": step_json.get("sla", {}),
                "action_available": step_json.get("actions_available", step_json.get("action_available", [])),
                "app_data": {
                    "assignee": [],
                    "personas": step_json.get("persona_required", step_json.get("personas", []))
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
            ReportTrackerService._set_assignee_timestamps_on_completion(current_step, current_time)
            
            # Create a new instance of the same step with fresh instance_id
            new_step_instance = ReportTrackerService._create_step_object(
                current_step_json, status="in_progress"
            )
            
            # Insert the new instance right after the current step
            steps.insert(current_step_index + 1, new_step_instance)
            ReportTrackerService._set_assignee_timestamps_on_activation(new_step_instance, current_time)
            return
        
        # =============================================================================
        # NORMAL FORWARD PROGRESSION
        # =============================================================================
        # Mark current step as completed and find the next step in progress tracker
        # =============================================================================
        current_step["status"] = "completed"
        current_step["completed_at"] = current_time
        ReportTrackerService._set_assignee_timestamps_on_completion(current_step, current_time)
        
        next_step_index = None
        for i in range(current_step_index + 1, len(steps)):
            if steps[i].get("step_id") == success_goto:
                next_step_index = i
                break

        if next_step_index is None:
            next_step_json = ReportTrackerService._find_step_in_workflow_json(
                workflow_json, success_goto
            )
            if next_step_json is None:
                raise UnprocessableEntityException(
                    detail=f"Next step {success_goto} not found in progress tracker"
                )
            for i in range(current_step_index + 1, len(steps)):
                if steps[i].get("step_id") == success_goto:
                    next_step_index = i
                    break
            if next_step_index is None:
                new_step = ReportTrackerService._create_step_object(
                    next_step_json, status="yet_to_start"
                )
                steps.insert(current_step_index + 1, new_step)
                next_step_index = current_step_index + 1

        if next_step_index is not None:
            for idx in range(current_step_index + 1, next_step_index):
                skipped_step = steps[idx]
                skipped_step_json = ReportTrackerService._find_step_in_workflow_json(
                    workflow_json, skipped_step.get("step_id")
                )
                if skipped_step_json and skipped_step_json.get("is_optional", skipped_step_json.get("skippable", False)):
                    skipped_step["status"] = "skipped"
                    skipped_step["completed_at"] = current_time
            next_step = steps[next_step_index]
            next_step["status"] = "in_progress"
            if not next_step.get("started_at"):
                next_step["started_at"] = current_time
            ReportTrackerService._set_assignee_timestamps_on_activation(next_step, current_time)
            
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
                    next_step_id = ReportTrackerService._get_default_transition(transitions.get("success_goto"))
                    
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
        
        # Tier 4: Last resort - completed step (e.g. auto-completed Published for reject+path)
        if current_step_index is None:
            for i in range(len(steps) - 1, -1, -1):
                if (steps[i].get("step_id") == current_step_id and
                        steps[i].get("status") == "completed"):
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
            ReportTrackerService._set_assignee_timestamps_on_completion(current_step, current_time)
            
            # Create a new instance of the same step with fresh instance_id
            new_step_instance = ReportTrackerService._create_step_object(
                current_step_json, status="in_progress"
            )
            
            # Insert the new instance right after the current step
            steps.insert(current_step_index + 1, new_step_instance)
            ReportTrackerService._set_assignee_timestamps_on_activation(new_step_instance, current_time)
            return
        
        # =============================================================================
        # NORMAL REJECTION FLOW (Go to different step)
        # =============================================================================
        # Walk the default success_goto chain from the workflow JSON to determine
        # the forward path (same chain that _build_happy_path uses).  For each
        # step_id in that chain, look for the latest existing instance *anywhere*
        # in the tracker (history AND forward yet_to_start steps) and clone it,
        # preserving accumulated app_data (assignees, personas, analytics, etc.).
        # Only fall back to _create_step_object for steps that have no instance
        # at all in the tracker.
        #
        # This ensures:
        #   - The forward path follows workflow defaults (user makes new choices)
        #   - Data accumulated on any previously visited step is preserved
        #   - Pre-assigned data on yet_to_start forward steps is preserved
        #     (assign_user_to_step_v2 works on steps in any status)
        # =============================================================================
        current_step["status"] = "rejected"
        current_step["completed_at"] = current_time
        ReportTrackerService._set_assignee_timestamps_on_completion(current_step, current_time)

        step_map: Dict[str, dict] = {}
        for step in workflow_json.get("steps", []):
            sid = step.get("step_id")
            if sid:
                step_map[sid] = step

        chain_step_ids: List[str] = []
        visited_chain: set = set()
        walker = fail_goto
        while walker and walker != "NA" and walker not in visited_chain:
            visited_chain.add(walker)
            if walker not in step_map:
                break
            chain_step_ids.append(walker)
            transitions = step_map[walker].get("transitions", {})
            success_goto_raw = transitions.get("success_goto")
            walker = ReportTrackerService._get_default_transition(success_goto_raw)

        cloned_steps: List[dict] = []
        last_search_index = len(steps) - 1
        for idx, chain_sid in enumerate(chain_step_ids):
            existing = ReportTrackerService._find_latest_instance_by_step_id(
                steps, chain_sid, last_search_index
            )
            if existing:
                clone = ReportTrackerService._clone_step_instance(existing, status="yet_to_start")
            else:
                step_json = step_map.get(chain_sid)
                if not step_json:
                    raise UnprocessableEntityException(
                        detail=f"Step JSON not found for step {chain_sid} in rejection chain"
                    )
                clone = ReportTrackerService._create_step_object(step_json, status="yet_to_start")

            if idx == 0:
                stage_name = clone.get("stage_name", "")
                is_auto_complete = ReportTrackerService._is_auto_complete_stage(stage_name)
                clone["status"] = "in_progress"
                clone["started_at"] = current_time
                if is_auto_complete:
                    clone["status"] = "completed"
                    clone["completed_at"] = current_time

            cloned_steps.append(clone)

        if not cloned_steps:
            raise UnprocessableEntityException(
                detail=f"Could not build rejection chain from {fail_goto} to {current_step_id}"
            )

        steps[:] = steps[:current_step_index + 1] + cloned_steps

        first_cloned = cloned_steps[0]
        if first_cloned["status"] == "in_progress":
            ReportTrackerService._set_assignee_timestamps_on_activation(first_cloned, current_time)

    @staticmethod
    async def update(db: AsyncSession, report_id: str, update_data) -> Optional[ReportTracker]:
        """
        Update a report tracker with workflow action and/or app_data.
        
        This method supports three use cases:
        1. Perform workflow action only (move forward/backward)
        2. Update step app_data only (no workflow state change)
        3. Both: perform action AND update app_data
        
        Supports 8 action types:
        - Forward actions (move to success_goto): accept, submit, approve
        - Backward actions (move to fail_goto): reject, push_back, pull_back
        - Special actions (no-op, TBD): publish, raise_exemption
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            update_data: Request containing optional action, instance_id, and/or app_data
            
        Returns:
            Updated ReportTracker instance, or None if not found
            
        Raises:
            UnprocessableEntityException: If action cannot be performed, step not found, or workflow is complete
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
        
        # Get optional fields from update_data
        action = getattr(update_data, "action", None)
        instance_id = getattr(update_data, "instance_id", None)
        app_data = getattr(update_data, "app_data", None)
        transition_path = getattr(update_data, "path", None)

        # Find target step based on instance_id or current in-progress step
        target_step = None

        if instance_id:
            # Find step by instance_id
            for step in steps:
                if step.get("instance_id") == instance_id:
                    target_step = step
                    break

            if not target_step:
                raise UnprocessableEntityException(
                    detail=f"Step with instance_id '{instance_id}' not found in progress tracker"
                )
        else:
            # Find current in-progress/retry step
            for step in steps:
                if step.get("status") in ["in_progress", "retry"]:
                    target_step = step
                    break

        # If action is provided, we need a valid target step for workflow operations
        if action:
            if not target_step and WorkflowActionType.is_forward_action(action):
                if ReportTrackerService._are_all_steps_completed(steps, workflow_json):
                    raise UnprocessableEntityException(
                        detail="All workflow steps are already completed. Cannot restart the workflow."
                    )

                if len(steps) > 0:
                    for step in steps:
                        if step.get("status") == "yet_to_start":
                            step["status"] = "in_progress"
                            step["started_at"] = datetime.now(timezone.utc).isoformat()
                            target_step = step
                            break

                    if not target_step:
                        raise UnprocessableEntityException(
                            detail="No step available to start"
                        )
                else:
                    raise UnprocessableEntityException(detail="No workflow steps found")

            if not target_step:
                # Backward action + path: allow last completed step as target (e.g. Published → unpublish/republish)
                if WorkflowActionType.is_backward_action(action) and transition_path:
                    last_step = steps[-1] if steps else None
                    if last_step and last_step.get("status") == "completed":
                        last_step_json = ReportTrackerService._find_step_in_workflow_json(
                            workflow_json, last_step.get("step_id")
                        )
                        fail_goto_raw = (last_step_json or {}).get("transitions", {}).get("fail_goto")
                        if fail_goto_raw and fail_goto_raw != "NA":
                            try:
                                resolved = ReportTrackerService._resolve_transition_path(
                                    fail_goto_raw, transition_path, "fail_goto"
                                )
                                if resolved and resolved != "NA":
                                    target_step = last_step
                            except UnprocessableEntityException:
                                pass
                if not target_step:
                    raise UnprocessableEntityException(detail="No step in progress or retry state found")

        # If only app_data is provided (no action), we still need a target step
        if not action and app_data is not None:
            if not target_step:
                raise UnprocessableEntityException(
                    detail="No step in progress or retry state found. Provide instance_id to target a specific step."
                )

        # Update app_data if provided
        if app_data is not None and target_step:
            target_step["app_data"] = app_data

        # Perform workflow action if provided
        if action and target_step:
            target_step_id = target_step.get("step_id")
            target_step_json = ReportTrackerService._find_step_in_workflow_json(workflow_json, target_step_id)

            if not target_step_json:
                raise UnprocessableEntityException(detail=f"Step JSON not found for step_id {target_step_id}")

            # Validate that the requested action is available for this step
            # Get action_available from the workflow JSON definition (source of truth)
            action_available = target_step_json.get("actions_available", target_step_json.get("action_available", []))

            # If action_available list is defined and not empty, validate the action
            # If action_available is empty list or missing, allow all configured actions (backward compatibility)
            if action_available and len(action_available) > 0:
                if action not in action_available:
                    raise UnprocessableEntityException(
                        detail=f"Action '{action}' is not allowed for step '{target_step_id}'. "
                               f"Available actions: {', '.join(action_available)}"
                    )
            # If action_available is empty list or missing, allow all actions (no validation needed)

            # Handle special actions (no-op for now)
            if WorkflowActionType.is_special_action(action):
                # codeql[py/log-injection]
                logger.info(f"Special action '{sanitize_log_input(action)}' executed (no-op) for step '{sanitize_log_input(target_step_id)}'")
            elif WorkflowActionType.is_forward_action(action):
                ReportTrackerService._accept(
                    tracker, steps, target_step, target_step_json, workflow_json, transition_path
                )
            elif WorkflowActionType.is_backward_action(action):
                ReportTrackerService._reject(
                    tracker, steps, target_step, target_step_json, workflow_json, transition_path
                )
            else:
                raise UnprocessableEntityException(detail=f"Invalid action: {action}")

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
    async def get_status(db: AsyncSession, report_id: str, include_audit: bool = True) -> Optional[Dict[str, Any]]:
        """
        Get the current workflow status for a specific report.
        
        Args:
            db: Async database session
            report_id: Unique identifier for the report
            include_audit: Reserved for future use - will control audit field visibility
            
        Returns:
            Dictionary with report_id and progress_tracker, or None if not found
        """
        tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if not tracker:
            return None
        
        progress_tracker = tracker.workflow_steps_json.get("progress_tracker", []) if tracker.workflow_steps_json else []
        
        # TODO: Figure out where to add due_date for each step in the existing /status API.
        # Steps are built in create_workflow_steps_json (schemas) and _build_happy_path (service);
        # they have 'sla' (may contain due_date) and 'app_data' but no top-level due_date.
        # Either add due_date when building step objects, or enrich each step here before returning.
        
        return {
            "report_id": tracker.report_id,
            "progress_tracker": progress_tracker
        }

    @staticmethod
    def _get_progress_tracker_exclude_first_assembler_step(progress_tracker: List[Any]) -> List[Any]:
        """
        Return the sublist of progress_tracker starting from the first step whose actor.type == "human".
        If no human step exists, return [].
        """
        for i, step in enumerate(progress_tracker):
            actor = step.get("actor") if isinstance(step, dict) else {}
            if isinstance(actor, dict) and actor.get("type") == "human":
                return progress_tracker[i:]
        return []

    @staticmethod
    async def get_status_exclude_first_assembler_step(db: AsyncSession, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow status for a report with progress_tracker starting from the first human step
        (excluding the leading agent assembler step). Same shape as get_status.
        Returns None if tracker not found.
        """
        status_data = await ReportTrackerService.get_status(db, report_id)
        if not status_data:
            return None
        progress_tracker = status_data.get("progress_tracker", [])
        status_data["progress_tracker"] = ReportTrackerService._get_progress_tracker_exclude_first_assembler_step(
            progress_tracker
        )
        return status_data

    @staticmethod
    def get_due_date(step: dict) -> str:
        """
        Return due_date for a step for use in status_lite response.
        TODO: Implement later - e.g. from step["app_data"].get("due_date") or
        step.get("sla", {}).get("due_date"). For now returns empty string.
        """
        return ""

    @staticmethod
    def format_date_for_lite(iso_string: Optional[str]) -> Optional[str]:
        """
        Convert ISO 8601 datetime to MM/DD/YYYY HH:MM:SS AM/PM for status_lite.
        Returns "" for missing/empty start date, None for missing completed date.

        TODO: Refactor into a shared utility (e.g. app.utils.date_utils or app.utils.format_utils). If the same
        ISO -> MM/DD/YYYY HH:MM:SS AM/PM logic exists elsewhere, call that function instead of duplicating.
        Do not change behavior or call sites until refactor.
        """
        if not iso_string or not iso_string.strip():
            return None
        try:
            from dateutil import parser as date_parser
            dt = date_parser.parse(iso_string)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.replace(tzinfo=timezone.utc)
            hour = dt.hour
            minute = dt.minute
            second = dt.second
            am_pm = "AM" if hour < 12 else "PM"
            hour12 = hour % 12 or 12
            return dt.strftime("%m/%d/%Y") + f" {hour12:02d}:{minute:02d}:{second:02d} {am_pm}"
        except (ValueError, TypeError):
            return None

    # TODO: Reusable getter functions for any computed/derived field from step or app_data (not just raw DB): single
    # place (this service or a small shared module) for assignee, role, start_date, completed_date, due_date, and
    # other derived values. One function per concept; use in status_lite, Pydantic models, and other callers.
    # (Note: _role_for_lite and _first_active_assignee_name are such getters.)

    @staticmethod
    def _role_for_lite(step: dict, assignee_value: str) -> str:
        """Return role string for lite stage: N/A when Unassigned, else first active assignee's role from app_data, then actor.role."""
        if assignee_value == "Unassigned":
            return "N/A"
        app_data = step.get("app_data") or {}
        assignees = app_data.get("assignee")
        if isinstance(assignees, list) and len(assignees) > 0:
            for a in assignees:
                if not ReportTrackerService._is_assignee_active(a):
                    continue
                role_raw = a.get("role")
                if role_raw is not None and str(role_raw).strip():
                    s = str(role_raw).strip()
                    return s.replace("_", " ").title() if s else "N/A"
        actor = step.get("actor") if isinstance(step.get("actor"), dict) else {}
        role_raw = actor.get("role") if actor else None
        if role_raw is None or str(role_raw).upper() in ("NA", "N/A", ""):
            return "N/A"
        s = str(role_raw).strip()
        return s.replace("_", " ").title() if s else "N/A"

    # TODO: get_role for lite (and any future role derivation) should be aligned with GET /status; _role_for_lite
    # (or a renamed shared helper) should be the single reusable function; refactor all callers to use it.

    @staticmethod
    def _first_active_assignee_name(step: dict) -> str:
        """First active assignee's user_name or name; if none or list empty return Unassigned."""
        app_data = step.get("app_data") or {}
        assignees = app_data.get("assignee")
        if not isinstance(assignees, list) or len(assignees) == 0:
            return "Unassigned"
        for a in assignees:
            if not ReportTrackerService._is_assignee_active(a):
                continue
            name = a.get("user_name") or a.get("name")
            if name and str(name).strip():
                return str(name).strip()
        return "Unassigned"

    @staticmethod
    def _progress_tracker_to_stages_lite(progress_tracker: List[Any]) -> List[Dict[str, Any]]:
        """
        Convert progress_tracker to list of stage dicts for status_lite.
        id = 1-based position (1, 2, 3, ...). Uniqueness in raw data is instance_id; not exposed.
        """
        stages: List[Dict[str, Any]] = []
        for i, step in enumerate(progress_tracker):
            if not isinstance(step, dict):
                continue
            step_id = i + 1
            title = (step.get("step_name") or step.get("step_id") or "").strip() or "—"
            assignee = ReportTrackerService._first_active_assignee_name(step)
            role = ReportTrackerService._role_for_lite(step, assignee)
            due_date = ReportTrackerService.get_due_date(step)
            started_at = step.get("started_at")
            start_date_val = ReportTrackerService.format_date_for_lite(started_at)
            start_date = start_date_val if start_date_val is not None else ""
            completed_at = step.get("completed_at")
            completed_date_val = ReportTrackerService.format_date_for_lite(completed_at)
            completed_date = completed_date_val if completed_date_val is not None else ""
            raw_status = step.get("status")
            status_str = (raw_status or "").strip() if raw_status is not None else ""
            stages.append({
                "id": step_id,
                "title": title,
                "assignee": assignee,
                "role": role,
                "due_date": due_date or "",
                "start_date": start_date,
                "completed_date": completed_date,
                "status": status_str,
            })
        return stages

    @staticmethod
    async def get_status_lite(
        db: AsyncSession,
        report_id: str,
        exclude_assembler: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """
        Get status in lite format: report_id + stages (snake_case, 1-based id, normalized status).
        If exclude_assembler True, stages start from first human step.
        """
        status_data = await ReportTrackerService.get_status(db, report_id)
        if not status_data:
            return None
        progress_tracker = status_data.get("progress_tracker", [])
        if exclude_assembler:
            progress_tracker = ReportTrackerService._get_progress_tracker_exclude_first_assembler_step(
                progress_tracker
            )
        stages = ReportTrackerService._progress_tracker_to_stages_lite(progress_tracker)
        return {
            "report_id": status_data["report_id"],
            "stages": stages,
        }

    @staticmethod
    def _normalize_actions_available(actions_raw: Any) -> List[str]:
        """Normalize action list for API response."""
        if not isinstance(actions_raw, list):
            return []
        actions: List[str] = []
        for value in actions_raw:
            if value is None:
                continue
            action = str(value).strip()
            if action:
                actions.append(action)
        return actions

    @staticmethod
    def _normalize_deduped_strings(values: List[Any]) -> List[str]:
        """Trim and dedupe string values while preserving order."""
        normalized: List[str] = []
        seen = set()
        for value in values:
            if value is None:
                continue
            normalized_value = str(value).strip()
            if not normalized_value or normalized_value in seen:
                continue
            normalized.append(normalized_value)
            seen.add(normalized_value)
        return normalized

    @staticmethod
    def _normalize_role_persona(role_raw: Any, persona_id_raw: Any) -> Optional[Dict[str, str]]:
        """Normalize a role/persona pair, skipping blanks."""
        role = str(role_raw).strip() if role_raw is not None else ""
        if not role:
            return None
        persona_id = str(persona_id_raw).strip() if persona_id_raw is not None else ""
        return {
            "role": role,
            "persona_id": persona_id,
        }

    @staticmethod
    def _dedupe_role_persona_items(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Dedupe role/persona items while preserving order."""
        deduped: List[Dict[str, str]] = []
        seen = set()
        for item in items:
            role = item.get("role", "")
            persona_id = item.get("persona_id", "")
            key = (role, persona_id)
            if key in seen:
                continue
            seen.add(key)
            deduped.append({"role": role, "persona_id": persona_id})
        return deduped

    @staticmethod
    def _current_step_roles_available(step: dict) -> List[Dict[str, str]]:
        """
        Resolve role/persona pairs available at the current step.

        Priority:
        1) Active assignee roles from app_data.assignee.
        2) app_data.personas role/persona data.
        3) Fallback to actor.role/persona when prior sources are unavailable.
        """
        app_data = step.get("app_data") or {}
        assignees = app_data.get("assignee")

        role_items: List[Dict[str, str]] = []
        if isinstance(assignees, list):
            for assignee in assignees:
                if not ReportTrackerService._is_assignee_active(assignee):
                    continue
                normalized = ReportTrackerService._normalize_role_persona(
                    assignee.get("role"),
                    assignee.get("persona_id"),
                )
                if normalized:
                    role_items.append(normalized)

        if role_items:
            return ReportTrackerService._dedupe_role_persona_items(role_items)

        personas = app_data.get("personas")
        if isinstance(personas, list):
            for persona in personas:
                if not isinstance(persona, dict):
                    continue
                normalized = ReportTrackerService._normalize_role_persona(
                    persona.get("role") or persona.get("name"),
                    persona.get("persona_id") or persona.get("id"),
                )
                if normalized:
                    role_items.append(normalized)
        if role_items:
            return ReportTrackerService._dedupe_role_persona_items(role_items)

        actor = step.get("actor") if isinstance(step.get("actor"), dict) else {}
        actor_item = ReportTrackerService._normalize_role_persona(
            actor.get("role") if actor else None,
            (actor.get("persona_id") or actor.get("id")) if actor else None,
        )
        if actor_item:
            return [actor_item]
        return []

    @staticmethod
    def _current_step_persona_ids(step: dict) -> List[int]:
        """
        Return deduped integer persona IDs from current step app_data.personas only.

        Source-of-truth rule for this API:
        - Use current_step.app_data.personas
        - Ignore assignee-level and actor-level persona_id fields
        """
        app_data = step.get("app_data") or {}
        personas_raw = app_data.get("personas")
        if not isinstance(personas_raw, list):
            return []

        persona_ids: List[int] = []
        seen = set()
        for value in personas_raw:
            if value is None:
                continue
            persona_value: Any = value
            if isinstance(value, dict):
                persona_value = value.get("persona_id", value.get("id"))
            try:
                persona_int = int(str(persona_value).strip())
            except (ValueError, TypeError):
                continue
            if persona_int in seen:
                continue
            seen.add(persona_int)
            persona_ids.append(persona_int)
        return persona_ids

    @staticmethod
    async def get_current_stage_summary(db: AsyncSession, report_id: str) -> Optional[Dict[str, Any]]:
        """
        Return current step details and current-step-focused workflow summary.

        Current step is the first step with status in ["in_progress", "retry"].
        """
        tracker = await ReportTrackerService.get_by_report_id(db, report_id)
        if not tracker:
            return None

        progress_tracker = tracker.workflow_steps_json.get("progress_tracker", []) if tracker.workflow_steps_json else []

        current_step_name: Optional[str] = None
        current_stage_name: Optional[str] = None
        actions_available: List[str] = []
        persona_id: List[int] = []
        steps: List[str] = []

        for step in progress_tracker:
            if not isinstance(step, dict):
                continue

            step_name = str(step.get("step_name") or step.get("step_id") or "").strip()
            if step_name:
                steps.append(step_name)

            step_status_raw = step.get("status")
            step_status = str(step_status_raw).strip() if step_status_raw is not None else ""

            if current_step_name is None and step_status in ("in_progress", "retry"):
                current_step_name = step_name or None
                current_stage_raw = step.get("stage_name")
                current_stage_name = str(current_stage_raw).strip() if current_stage_raw is not None else None
                actions_available = ReportTrackerService._normalize_actions_available(
                    step.get("action_available", [])
                )
                persona_id = ReportTrackerService._current_step_persona_ids(step)

        return {
            "report_id": tracker.report_id,
            "current_step_name": current_step_name,
            "current_stage_name": current_stage_name,
            "steps": steps,
            "actions_available": actions_available,
            "persona_id": persona_id,
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

    @staticmethod
    def _is_assignee_active(assignee: dict) -> bool:
        """Check whether an assignee record is currently active.

        Handles both v1 records (no ``status`` key, treated as active)
        and v2 records (explicit ``status`` field).
        """
        if not isinstance(assignee, dict):
            return False
        status = assignee.get("status")
        if status is None:
            return True
        return status == "active"

    @staticmethod
    def _set_assignee_timestamps_on_completion(step: dict, current_time: str) -> None:
        """Set ``completed_at`` on every active assignee of *step*."""
        assignees = (step.get("app_data") or {}).get("assignee")
        if not isinstance(assignees, list):
            return
        for a in assignees:
            if ReportTrackerService._is_assignee_active(a):
                a["completed_at"] = current_time

    @staticmethod
    def _set_assignee_timestamps_on_activation(step: dict, current_time: str) -> None:
        """Set ``started_at`` on every active assignee whose ``started_at`` is still ``None``."""
        assignees = (step.get("app_data") or {}).get("assignee")
        if not isinstance(assignees, list):
            return
        for a in assignees:
            if ReportTrackerService._is_assignee_active(a) and a.get("started_at") is None:
                a["started_at"] = current_time

    @staticmethod
    async def assign_user_to_step_v2(
        db: AsyncSession,
        report_id: str,
        instance_id: str,
        user_id: str,
        user_name: str,
        user_email: str,
        role: str,
    ) -> Optional[ReportTracker]:
        """
        Assign a user to a workflow step identified by instance_id (v2).

        Deactivates all currently active assignees on the target step, then
        appends a new assignee record with full lifecycle timestamps.  Works
        on steps in any status (yet_to_start, in_progress, completed, retry).

        Returns:
            Updated ReportTracker, or None if report_id not found.

        Raises:
            UnprocessableEntityException: If instance_id not found in progress_tracker.
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
            if step.get("instance_id") == instance_id:
                target_step = step
                break

        if not target_step:
            raise UnprocessableEntityException(
                detail=f"Step with instance_id '{instance_id}' not found in progress tracker"
            )

        if "app_data" not in target_step:
            target_step["app_data"] = {}
        if not isinstance(target_step["app_data"].get("assignee"), list):
            target_step["app_data"]["assignee"] = []

        current_time = datetime.now(timezone.utc).isoformat()

        for a in target_step["app_data"]["assignee"]:
            if ReportTrackerService._is_assignee_active(a):
                a["status"] = "inactive"
                a["unassigned_at"] = current_time

        step_status = target_step.get("status")
        started_at = current_time if step_status in ("in_progress", "retry") else None

        assignee_object = {
            "user_id": user_id,
            "user_name": user_name,
            "user_email": user_email,
            "role": role,
            "status": "active",
            "assigned_at": current_time,
            "started_at": started_at,
            "completed_at": None,
            "unassigned_at": None,
        }

        target_step["app_data"]["assignee"].append(assignee_object)

        tracker.workflow_steps_json = {"progress_tracker": steps}
        flag_modified(tracker, "workflow_steps_json")
        await db.commit()
        await db.refresh(tracker)

        return tracker

