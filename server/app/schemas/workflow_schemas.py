from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class WorkflowListItem(BaseModel):
    workflow_id: int
    name: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    items: List[WorkflowListItem]
    total: int


class WorkflowDetail(BaseModel):
    workflow_id: int
    name: Optional[str] = None
    is_active: bool
    workflow_json: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowUpdateRequest(BaseModel):
    name: Optional[str] = None
    is_active: Optional[bool] = None
    workflow_json: Optional[Dict[str, Any]] = None
