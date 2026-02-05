"""Workspace domain entities."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any
from uuid import UUID, uuid4


class WorkspaceRole(IntEnum):
    """Workspace role hierarchy. Higher value = more permissions.

    Use >= comparison for permission checks:
        user_role >= WorkspaceRole.ADMIN  # True if Admin or Owner
    """

    VIEWER = 10
    MEMBER = 20
    ADMIN = 30
    OWNER = 40


def has_permission(user_role: WorkspaceRole, required_role: WorkspaceRole) -> bool:
    """Check if a user role meets the required permission level."""
    return user_role >= required_role


@dataclass
class Workspace:
    """Domain entity for a Workspace."""

    name: str
    created_by: UUID
    id: UUID = field(default_factory=uuid4)
    slug: str = ""
    description: str | None = None
    settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self) -> None:
        """Ensure updated_at is always at least as recent as created_at."""
        if self.updated_at < self.created_at:
            self.updated_at = self.created_at


@dataclass
class WorkspaceMember:
    """Domain entity for a workspace membership."""

    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole = WorkspaceRole.MEMBER
    joined_at: datetime = field(default_factory=datetime.utcnow)
    invited_by: UUID | None = None
