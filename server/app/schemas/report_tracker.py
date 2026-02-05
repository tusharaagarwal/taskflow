from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional, Literal, Any, Dict
from datetime import datetime, timezone
from uuid import UUID
import uuid

from app.constants import WorkflowActionType


def get_workflow_json() -> dict:
    """
    Return an empty workflow JSON structure.
    
    Returns:
        Empty dictionary for workflow initialization
    """
    return {}


def generate_report_id() -> str:
    """
    Generate a unique report identifier with timestamp and random component.
    
    Returns:
        Report ID in format 'RPT-YYYYMMDDHHMMSS-XXXXXXXX'
    """
    from datetime import datetime, timezone
    import secrets
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    random_suffix = secrets.token_hex(4).upper()
    return f"RPT-{timestamp}-{random_suffix}"


class ReportTrackerCreateRequest(BaseModel):
    """
    Request schema for creating a new report tracker.
    
    Attributes:
        transaction_id: Transaction identifier
        pr_id: PR identifier
        content_type: Type of content (replaces content_product_name)
        lob: Line of Business
        sub_lob: Sub Line of Business
        document_type: Document type for auto-generating report ID (e.g., "ANNUAL" -> "ANN-100001")
        action_code: Action code (stored as-is)
    """
    transaction_id: str = Field(..., description="Transaction identifier")
    pr_id: str = Field(..., description="PR identifier")
    content_type: str = Field(..., description="Type of content product")
    lob: str = Field(..., description="Line of Business")
    sub_lob: str = Field(..., description="Sub Line of Business")
    document_type: str = Field(..., description="Document type for auto-generating report ID")
    action_code: str = Field(..., description="Action code")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "transaction_id": "TXN-12345",
                "pr_id": "PR-67890",
                "content_type": "Credit Opinion",
                "lob": "banking",
                "sub_lob": "figbanking",
                "document_type": "Credit Opinion",
                "action_code": "APPROVED"
            }
        }
    )

    @classmethod
    def create_workflow_steps_json(cls, workflow_json: Optional[dict] = None) -> dict:
        """
        Build the complete workflow progress tracker with all happy path steps.
        
        Each step receives a unique instance_id (UUID) for precise identification,
        even when the same step_id appears multiple times due to rejections.
        
        The first step is initialized as 'in_progress', all others as 'yet_to_start'.
        Auto-complete stages (e.g., 'Published') are completed immediately when activated.
        
        Args:
            workflow_json: Workflow definition containing steps and transitions
            
        Returns:
            Dictionary with 'progress_tracker' containing all workflow step instances
        """
        if not workflow_json or "steps" not in workflow_json or len(workflow_json["steps"]) == 0:
            return {"progress_tracker": []}
        
        progress_tracker = []
        current_time = datetime.now(timezone.utc).isoformat()
        
        step_map = {}
        for step in workflow_json["steps"]:
            step_id = step.get("step_id")
            if step_id:
                step_map[step_id] = step
        
        first_step_json = workflow_json["steps"][0]
        first_step_id = first_step_json.get("step_id")
        
        if not first_step_id:
            return {"progress_tracker": []}
        
        visited_steps = set()
        current_step_id = first_step_id
        
        while current_step_id and current_step_id != "NA" and current_step_id not in visited_steps:
            visited_steps.add(current_step_id)
            step_json = step_map.get(current_step_id)
            
            if not step_json:
                break
            
            stage_name = step_json.get("stage_name", "")
            is_auto_complete = stage_name == "Published"
            
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
            
            if len(progress_tracker) == 0:
                step_obj["status"] = "in_progress"
                step_obj["started_at"] = current_time
                if is_auto_complete:
                    step_obj["status"] = "completed"
                    step_obj["completed_at"] = current_time
            else:
                step_obj["status"] = "yet_to_start"
            
            progress_tracker.append(step_obj)
            
            transitions = step_json.get("transitions", {})
            success_goto_raw = transitions.get("success_goto")
            # Get default transition for building happy path
            current_step_id = cls._get_default_transition(success_goto_raw)
        
        return {"progress_tracker": progress_tracker}
    
    @classmethod
    def _get_default_transition(cls, transition_value) -> Optional[str]:
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
                return cls._get_default_transition(default_value)
        
        return None


class ReportTrackerUpdateRequest(BaseModel):
    """
    Request schema for updating workflow progress or step app_data.
    
    This endpoint supports three use cases:
    1. Perform workflow action only (move forward/backward)
    2. Update step app_data only (no workflow state change)
    3. Both: perform action AND update app_data
    
    At least one of 'action' or 'app_data' must be provided.
    
    Attributes:
        action: Optional workflow action type (forward/backward/special)
        path: Optional path for dynamic transition resolution
        instance_id: Optional UUID to target a specific step (otherwise targets current in-progress step)
        app_data: Optional flexible dictionary to replace the step's app_data
    """
    action: Optional[Literal[
        "accept", "submit", "approve",  # Forward actions
        "reject", "push_back", "pull_back",  # Backward actions
        "publish", "raise_exemption"  # Special actions (TBD)
    ]] = Field(
        None,
        description="Workflow action to perform. Forward actions (accept/submit/approve) move to next step. "
                    "Backward actions (reject/push_back/pull_back) move to previous step. "
                    "Optional if only updating app_data."
    )
    path: Optional[str] = Field(
        None,
        description="Path for dynamic transition resolution (e.g., 'exemption/errc/approved'). "
                    "Used when transitions have nested conditional paths instead of simple string values."
    )
    instance_id: Optional[str] = Field(
        None,
        description="UUID of specific step instance to update. "
                    "If not provided, targets the current in-progress/retry step. "
                    "Use this to update app_data of any step in the progress tracker."
    )
    app_data: Optional[Dict[str, Any]] = Field(
        None,
        description="Flexible dictionary to replace the step's app_data. "
                    "Consumer applications fully control the content structure. "
                    "This completely replaces the existing app_data of the target step."
    )
    
    @model_validator(mode='after')
    def validate_at_least_one_field(self) -> 'ReportTrackerUpdateRequest':
        """Ensure at least one of 'action' or 'app_data' is provided."""
        if self.action is None and self.app_data is None:
            raise ValueError("At least one of 'action' or 'app_data' must be provided")
        return self
    
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Action only - Accept current step",
                    "value": {
                        "action": "accept"
                    }
                },
                {
                    "summary": "Action with path - Accept with dynamic transition",
                    "value": {
                        "action": "accept",
                        "path": "exemption/errc/approved"
                    }
                },
                {
                    "summary": "App_data only - Update current step",
                    "value": {
                        "app_data": {
                            "assignee": [
                                {"user_id": "user-123", "name": "John Doe", "email": "john@example.com"}
                            ],
                            "custom_field": "any value",
                            "metadata": {"source": "crm_app"}
                        }
                    }
                },
                {
                    "summary": "Update specific step by instance_id",
                    "value": {
                        "instance_id": "550e8400-e29b-41d4-a716-446655440000",
                        "app_data": {
                            "reviewed": True,
                            "review_notes": "Looks good"
                        }
                    }
                },
                {
                    "summary": "Action + app_data - Submit and update",
                    "value": {
                        "action": "submit",
                        "app_data": {
                            "submitted_by": "jane@example.com",
                            "submission_notes": "Ready for review"
                        }
                    }
                }
            ]
        }
    )


class ReportTrackerStatusResponse(BaseModel):
    """
    Response schema for workflow status queries.
    
    Attributes:
        report_id: Unique identifier for the report
        progress_tracker: List of all step instances in the workflow
    """
    report_id: str
    progress_tracker: list

    model_config = ConfigDict(from_attributes=True)


class ReportTrackerWorkflowResponse(BaseModel):
    """
    Response schema for workflow definition queries.
    
    Returns the workflow JSON definition for a report tracker.
    
    Attributes:
        report_id: Unique identifier for the report
        workflow_json: Complete workflow definition with steps and transitions
    """
    report_id: str
    workflow_json: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class ReportTrackerStatusUpdateRequest(BaseModel):
    """
    Extended request schema for status updates with assignee details.
    
    Supports 8 action types:
    - Forward actions (move to success_goto): accept, submit, approve
    - Backward actions (move to fail_goto): reject, push_back, pull_back
    - Special actions (no-op, TBD): publish, raise_exemption
    
    Attributes:
        action: Workflow action type
        path: Optional path for dynamic transition resolution
        assignee: Optional email of person assigned to next step
        role: Optional role designation for assignee
        start_date: Optional start date in ISO 8601 format
        due_date: Optional due date in ISO 8601 format
    """
    action: Literal[
        "accept", "submit", "approve",  # Forward actions
        "reject", "push_back", "pull_back",  # Backward actions
        "publish", "raise_exemption"  # Special actions (TBD)
    ]
    path: Optional[str] = Field(
        None,
        description="Path for dynamic transition resolution (e.g., 'exemption/errc/approved'). "
                    "Used when transitions have nested conditional paths instead of simple string values.",
        json_schema_extra={"example": "exemption/errc/approved"}
    )
    assignee: Optional[str] = Field(
        None,
        description="The person assigned to the next step"
    )
    role: Optional[str] = Field(
        None,
        description="The role of the assignee for the next step"
    )
    start_date: Optional[str] = Field(
        None,
        alias="startDate",
        description="The start date for the next step in ISO 8601 format"
    )
    due_date: Optional[str] = Field(
        None,
        alias="dueDate",
        description="The due date for the next step in ISO 8601 format"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "action": "accept",
                "path": "exemption/errc/approved",
                "assignee": "john.doe@example.com",
                "role": "Senior Analyst",
                "startDate": "2025-11-01T09:00:00Z",
                "dueDate": "2025-11-15T18:00:00Z"
            }
        }
    )


class ReportTrackerListResponse(BaseModel):
    """
    Lightweight response schema for listing report trackers.
    
    Attributes:
        id: Database primary key
        report_id: Unique identifier for the report
    """
    id: UUID
    report_id: str

    model_config = ConfigDict(from_attributes=True)


class ReportTrackerResponse(BaseModel):
    """
    Complete response schema for report tracker details.
    
    Attributes:
        id: Database primary key
        report_id: Auto-generated unique identifier for the report
        transaction_id: Transaction identifier
        pr_id: PR identifier
        cpm_id: CPM record ID
        action_code: Action code
        workflow_json: Complete workflow definition
        workflow_steps_json: Current state of all workflow steps
        created_at: Timestamp of tracker creation
        updated_at: Timestamp of last update
    """
    id: UUID
    report_id: str
    transaction_id: Optional[str] = None
    pr_id: Optional[str] = None
    cpm_id: Optional[str] = None
    action_code: Optional[str] = None
    workflow_json: Optional[dict] = None
    workflow_steps_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AssignUserToStepRequest(BaseModel):
    """
    Request schema for assigning a user to a workflow step.
    
    Attributes:
        report_id: Unique identifier for the report
        stage_name: Name of the workflow stage
        step_name: Name of the specific step
        user_id: Unique identifier for the user
        user_name: Display name of the user
        user_email: Email address of the user
        role: Optional role designation for this assignment
    """
    report_id: str = Field(..., description="Report ID")
    stage_name: str = Field(..., description="Name of the stage")
    step_name: str = Field(..., description="Name of the step")
    user_id: str = Field(..., description="User ID")
    user_name: str = Field(..., description="User name")
    user_email: str = Field(..., description="User email")
    role: Optional[str] = Field(None, description="Role of the user")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "report_id": "PR-123",
                "stage_name": "Authoring",
                "step_name": "Initial Draft",
                "user_id": "user-123",
                "user_name": "John Doe",
                "user_email": "john.doe@example.com",
                "role": "Senior Analyst"
            }
        }
    )
