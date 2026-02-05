"""Pydantic schemas for Notification API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NotificationResponse(BaseModel):
    """Single notification in the feed."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID  # notification_recipient.id (used for mark_read/delete)
    notification_id: UUID
    type: str  # notification_type.name (e.g., "task.completed")
    workspace_id: UUID
    actor_id: UUID
    entity_type: str
    entity_id: UUID
    metadata: dict[str, Any]
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime


class NotificationListResponse(BaseModel):
    """Paginated notification feed response."""

    data: list[NotificationResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class UnreadCountResponse(BaseModel):
    """Unread notification count response."""

    count: int


class MarkAllReadResponse(BaseModel):
    """Response for mark-all-read operation."""

    count: int  # Number of notifications marked


class NotificationTypeResponse(BaseModel):
    """Notification type definition."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    description: str | None = None
    template: str
    is_mandatory: bool


class NotificationTypeListResponse(BaseModel):
    """List of notification types."""

    data: list[NotificationTypeResponse]


class NotificationPreferenceRequest(BaseModel):
    """Schema for creating/updating a notification preference."""

    channel: str = Field(..., pattern="^(in_app|email)$")
    enabled: bool
    workspace_id: UUID | None = None
    notification_type: str | None = None


class NotificationPreferenceResponse(BaseModel):
    """Notification preference response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    channel: str
    enabled: bool
    workspace_id: UUID | None = None
    notification_type: str | None = None


class NotificationPreferenceListResponse(BaseModel):
    """List of notification preferences."""

    data: list[NotificationPreferenceResponse]
