from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any


class WorkflowBase(BaseModel):
    workflow_name: Optional[str]
    report_type: Optional[str]
    stages: Optional[Any]
    note: Optional[str] = None


class WorkflowOut(WorkflowBase):
    workflow_id: int
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True
