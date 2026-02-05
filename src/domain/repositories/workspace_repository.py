"""Workspace repository protocol."""

from typing import Protocol
from uuid import UUID

from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole


class IWorkspaceRepository(Protocol):
    """Repository interface for Workspace entities."""

    async def get(self, id: UUID) -> Workspace | None:
        """Get a workspace by ID."""
        ...

    async def get_by_slug(self, slug: str) -> Workspace | None:
        """Get a workspace by slug."""
        ...

    async def get_all_for_user(self, user_id: UUID) -> list[Workspace]:
        """Get all workspaces a user is a member of."""
        ...

    async def create(self, workspace: Workspace) -> Workspace:
        """Create a new workspace."""
        ...

    async def update(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace."""
        ...

    async def delete(self, id: UUID) -> bool:
        """Delete a workspace and return success status."""
        ...

    async def get_member(self, workspace_id: UUID, user_id: UUID) -> WorkspaceMember | None:
        """Get a workspace member by workspace and user IDs."""
        ...

    async def get_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        """Get all members of a workspace."""
        ...

    async def add_member(self, member: WorkspaceMember) -> WorkspaceMember:
        """Add a member to a workspace."""
        ...

    async def update_member_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Update a member's role in a workspace."""
        ...

    async def remove_member(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Remove a member from a workspace."""
        ...

    async def count_members(self, workspace_id: UUID) -> int:
        """Count the number of members in a workspace."""
        ...

    async def count_owners(self, workspace_id: UUID) -> int:
        """Count the number of owners in a workspace."""
        ...
