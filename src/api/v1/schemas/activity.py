"""Pydantic schemas for Activity API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityLogResponse(BaseModel):
    """Schema for an activity log entry response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    actor_id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime


class ActivityListResponse(BaseModel):
    """Schema for paginated activity log response."""

    data: list[ActivityLogResponse]
    meta: dict[str, Any] = Field(default_factory=dict)
