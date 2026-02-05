"""Activity log domain entity and action constants."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

# --- Activity Action Constants ---
# Format: {entity_type}.{action}


class Actions:
    """Activity action constants using dot-notation."""

    # Todo actions
    TODO_CREATED = "todo.created"
    TODO_UPDATED = "todo.updated"
    TODO_COMPLETED = "todo.completed"
    TODO_UNCOMPLETED = "todo.uncompleted"
    TODO_DELETED = "todo.deleted"
    TODO_MOVED = "todo.moved"

    # Tag actions
    TAG_CREATED = "tag.created"
    TAG_UPDATED = "tag.updated"
    TAG_DELETED = "tag.deleted"
    TAG_ATTACHED = "tag.attached"
    TAG_DETACHED = "tag.detached"

    # Workspace actions
    WORKSPACE_UPDATED = "workspace.updated"
    WORKSPACE_DELETED = "workspace.deleted"

    # Member actions
    MEMBER_ADDED = "member.added"
    MEMBER_REMOVED = "member.removed"
    MEMBER_LEFT = "member.left"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_OWNERSHIP_TRANSFERRED = "member.ownership_transferred"

    # Invitation actions
    INVITATION_CREATED = "invitation.created"
    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_REVOKED = "invitation.revoked"


@dataclass
class ActivityLog:
    """Domain entity for an activity log entry."""

    workspace_id: UUID
    actor_id: UUID
    action: str
    entity_type: str
    entity_id: UUID
    id: UUID = field(default_factory=uuid4)
    changes: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
