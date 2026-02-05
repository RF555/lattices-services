"""Group domain entities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4


class GroupRole(str, Enum):
    """Role within a group."""

    ADMIN = "admin"
    MEMBER = "member"


@dataclass
class Group:
    """Domain entity for a workspace group."""

    workspace_id: UUID
    name: str
    created_by: UUID
    id: UUID = field(default_factory=uuid4)
    description: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class GroupMember:
    """Domain entity for a group membership."""

    group_id: UUID
    user_id: UUID
    role: GroupRole = GroupRole.MEMBER
    joined_at: datetime = field(default_factory=datetime.utcnow)
