"""Activity log repository protocol."""

from typing import List, Protocol
from uuid import UUID

from domain.entities.activity import ActivityLog


class IActivityRepository(Protocol):
    """Repository interface for ActivityLog entities."""

    async def create(self, activity: ActivityLog) -> ActivityLog:
        """Create a new activity log entry."""
        ...

    async def get_for_workspace(
        self,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ActivityLog]:
        """Get activity log entries for a workspace, ordered by newest first."""
        ...

    async def get_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        limit: int = 50,
    ) -> List[ActivityLog]:
        """Get activity log entries for a specific entity."""
        ...

    async def get_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> List[ActivityLog]:
        """Get activity log entries by a specific user."""
        ...
