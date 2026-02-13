"""Notification domain entities and type constants."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

# --- Notification Type Constants ---
# Format: {entity_type}.{action}


class NotificationTypes:
    """Notification type constants using dot-notation."""

    # Task notifications
    TASK_COMPLETED = "task.completed"
    TASK_UPDATED = "task.updated"
    TASK_CREATED = "task.created"
    TASK_DELETED = "task.deleted"
    TASK_MOVED_WORKSPACE = "task.moved_workspace"

    # Member notifications
    MEMBER_ADDED = "member.added"
    MEMBER_REMOVED = "member.removed"
    MEMBER_ROLE_CHANGED = "member.role_changed"

    # Invitation notifications
    INVITATION_RECEIVED = "invitation.received"
    INVITATION_ACCEPTED = "invitation.accepted"

    # Group notifications
    GROUP_MEMBER_ADDED = "group.member_added"


@dataclass
class NotificationType:
    """Domain entity for a notification type definition."""

    name: str
    template: str
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    default_channels: list[str] = field(default_factory=lambda: ["in_app"])
    is_mandatory: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Notification:
    """Domain entity for a notification event."""

    type_name: str
    workspace_id: UUID
    actor_id: UUID
    entity_type: str
    entity_id: UUID
    id: UUID = field(default_factory=uuid4)
    type_id: UUID | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


@dataclass
class NotificationRecipient:
    """Domain entity for a per-user notification delivery record."""

    notification_id: UUID
    recipient_id: UUID
    id: UUID = field(default_factory=uuid4)
    is_read: bool = False
    read_at: datetime | None = None
    is_deleted: bool = False
    deleted_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class NotificationView:
    """Read-only value object: denormalized notification for the API layer."""

    id: UUID
    notification_id: UUID
    type: str
    workspace_id: UUID
    actor_id: UUID
    entity_type: str
    entity_id: UUID
    metadata: dict[str, Any]
    is_read: bool
    read_at: datetime | None
    created_at: datetime


@dataclass
class NotificationPreference:
    """Domain entity for a user's notification preference."""

    user_id: UUID
    channel: str = "in_app"
    id: UUID = field(default_factory=uuid4)
    workspace_id: UUID | None = None
    notification_type: str | None = None
    enabled: bool = True
