from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RuntimeAppConfigResponse(BaseModel):
    """Full runtime config map and timestamp (singleton row)."""

    model_config = ConfigDict(from_attributes=True)

    data: dict[str, Any]
    updated_at: datetime


class RuntimeAppConfigPatchBody(BaseModel):
    """Payload merged shallowly into the stored `data` map."""

    data: dict[str, Any] = Field(
        ...,
        description="Key-value pairs shallow-merged into the persisted JSON map",
    )
