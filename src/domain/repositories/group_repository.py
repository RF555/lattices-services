"""Group repository protocol."""

from typing import Protocol
from uuid import UUID

from domain.entities.group import Group, GroupMember, GroupRole


class IGroupRepository(Protocol):
    """Repository interface for Group entities."""

    async def get(self, id: UUID) -> Group | None:
        """Get a group by ID."""
        ...

    async def get_for_workspace(self, workspace_id: UUID) -> list[Group]:
        """Get all groups in a workspace."""
        ...

    async def create(self, group: Group) -> Group:
        """Create a new group."""
        ...

    async def update(self, group: Group) -> Group:
        """Update an existing group."""
        ...

    async def delete(self, id: UUID) -> bool:
        """Delete a group."""
        ...

    async def get_member(
        self, group_id: UUID, user_id: UUID
    ) -> GroupMember | None:
        """Get a specific group member."""
        ...

    async def get_members(self, group_id: UUID) -> list[GroupMember]:
        """Get all members of a group."""
        ...

    async def add_member(self, member: GroupMember) -> GroupMember:
        """Add a member to a group."""
        ...

    async def update_member_role(
        self, group_id: UUID, user_id: UUID, role: GroupRole
    ) -> GroupMember:
        """Update a group member's role."""
        ...

    async def remove_member(self, group_id: UUID, user_id: UUID) -> bool:
        """Remove a member from a group."""
        ...

    async def count_members(self, group_id: UUID) -> int:
        """Count members in a group."""
        ...
