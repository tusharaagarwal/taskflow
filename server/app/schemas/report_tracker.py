from pydantic import BaseModel, Field
from typing import Optional, Literal
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
        report_id: Unique identifier for the report
        content_product_name: Name of the content product defining the workflow
        lob: Line of Business
        sub_lob: Sub Line of Business
    """
    report_id: str = Field(..., example="PR-123", description="Unique identifier for the report")
    content_product_name: str = Field(..., example="Credit Opinion", description="Name of the content product")
    lob: str = Field(..., example="banking", description="Line of Business")
    sub_lob: str = Field(..., example="figbanking", description="Sub Line of Business")

    class Config:
        json_schema_extra = {
            "example": {
                "report_id": "PR-123",
                "content_product_name": "Credit Opinion",
                "lob": "banking",
                "sub_lob": "figbanking"
            }
        }

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
    Request schema for updating workflow progress.
    
    Supports 8 action types:
    - Forward actions (move to success_goto): accept, submit, approve
    - Backward actions (move to fail_goto): reject, push_back, pull_back
    - Special actions (no-op, TBD): publish, raise_exemption
    
    Attributes:
        action: Workflow action type
        path: Optional path for dynamic transition resolution (e.g., 'exemption/errc/approved')
              Used to navigate nested transition objects when success_goto or fail_goto
              contains conditional paths instead of a simple string.
    """
    action: Literal[
        "accept", "submit", "approve",  # Forward actions
        "reject", "push_back", "pull_back",  # Backward actions
        "publish", "raise_exemption"  # Special actions (TBD)
    ] = Field(
        ...,
        description="Action to perform: forward actions (accept/submit/approve), backward actions (reject/push_back/pull_back), or special actions (publish/raise_exemption - TBD)",
        example="accept"
    )
    path: Optional[str] = Field(
        None,
        description="Path for dynamic transition resolution (e.g., 'exemption/errc/approved'). "
                    "Used when transitions have nested conditional paths instead of simple string values.",
        example="exemption/errc/approved"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "action": "accept",
                "path": "exemption/errc/approved"
            }
        }


class ReportTrackerStatusResponse(BaseModel):
    """
    Response schema for workflow status queries.
    
    Attributes:
        report_id: Unique identifier for the report
        progress_tracker: List of all step instances in the workflow
    """
    report_id: str
    progress_tracker: list

    class Config:
        from_attributes = True


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
        example="exemption/errc/approved"
    )
    assignee: Optional[str] = Field(
        None,
        description="The person assigned to the next step",
        example="john.doe@example.com"
    )
    role: Optional[str] = Field(
        None,
        description="The role of the assignee for the next step",
        example="Reviewer"
    )
    start_date: Optional[str] = Field(
        None,
        alias="startDate",
        description="The start date for the next step in ISO 8601 format",
        example="2025-11-01T09:00:00Z"
    )
    due_date: Optional[str] = Field(
        None,
        alias="dueDate",
        description="The due date for the next step in ISO 8601 format",
        example="2025-11-15T18:00:00Z"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "action": "accept",
                "path": "exemption/errc/approved",
                "assignee": "john.doe@example.com",
                "role": "Senior Analyst",
                "startDate": "2025-11-01T09:00:00Z",
                "dueDate": "2025-11-15T18:00:00Z"
            }
        }


class ReportTrackerListResponse(BaseModel):
    """
    Lightweight response schema for listing report trackers.
    
    Attributes:
        id: Database primary key
        report_id: Unique identifier for the report
    """
    id: UUID
    report_id: str

    class Config:
        from_attributes = True


class ReportTrackerResponse(BaseModel):
    """
    Complete response schema for report tracker details.
    
    Attributes:
        id: Database primary key
        report_id: Unique identifier for the report
        workflow_json: Complete workflow definition
        workflow_steps_json: Current state of all workflow steps
        created_at: Timestamp of tracker creation
        updated_at: Timestamp of last update
    """
    id: UUID
    report_id: str
    workflow_json: Optional[dict] = None
    workflow_steps_json: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    report_id: str = Field(..., description="Report ID", example="PR-123")
    stage_name: str = Field(..., description="Name of the stage", example="Authoring")
    step_name: str = Field(..., description="Name of the step", example="Initial Draft")
    user_id: str = Field(..., description="User ID", example="user-123")
    user_name: str = Field(..., description="User name", example="John Doe")
    user_email: str = Field(..., description="User email", example="john.doe@example.com")
    role: Optional[str] = Field(None, description="Role of the user", example="Senior Analyst")
    
    class Config:
        json_schema_extra = {
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