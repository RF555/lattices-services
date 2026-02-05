"""Activity service layer for logging and querying workspace activity."""

from collections.abc import Callable
from typing import Any
from uuid import UUID

from core.exceptions import NotAMemberError, WorkspaceNotFoundError
from domain.entities.activity import ActivityLog
from domain.repositories.unit_of_work import IUnitOfWork


class ActivityService:
    """Service layer for activity logging and retrieval."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def log(
        self,
        uow: IUnitOfWork,
        workspace_id: UUID,
        actor_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        changes: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ActivityLog:
        """Log an activity within an existing UoW transaction.

        This method is designed to be called from other services
        within their existing transaction context.

        Args:
            uow: The active Unit of Work (caller manages commit).
            workspace_id: The workspace where the activity occurred.
            actor_id: The user who performed the action.
            action: The action string (use Actions constants).
            entity_type: The type of entity affected.
            entity_id: The ID of the entity affected.
            changes: Optional dict of field-level changes {field: {old, new}}.
            metadata: Optional additional metadata.

        Returns:
            The created ActivityLog entry.
        """
        activity = ActivityLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )
        return await uow.activities.create(activity)

    async def get_workspace_activity(
        self,
        workspace_id: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[ActivityLog]:
        """Get activity feed for a workspace. Requires membership.

        Args:
            workspace_id: The workspace to get activity for.
            user_id: The requesting user (must be a member).
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of activity log entries, newest first.
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            member = await uow.workspaces.get_member(workspace_id, user_id)
            if not member:
                raise NotAMemberError(str(workspace_id))

            return await uow.activities.get_for_workspace(  # type: ignore[no-any-return]
                workspace_id, limit=limit, offset=offset
            )

    async def get_entity_history(
        self,
        workspace_id: UUID,
        user_id: UUID,
        entity_type: str,
        entity_id: UUID,
        limit: int = 50,
    ) -> list[ActivityLog]:
        """Get activity history for a specific entity. Requires membership.

        Args:
            workspace_id: The workspace context.
            user_id: The requesting user (must be a member).
            entity_type: The entity type to filter by.
            entity_id: The entity ID to filter by.
            limit: Maximum number of entries to return.

        Returns:
            List of activity log entries for the entity, newest first.
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            member = await uow.workspaces.get_member(workspace_id, user_id)
            if not member:
                raise NotAMemberError(str(workspace_id))

            return await uow.activities.get_for_entity(  # type: ignore[no-any-return]
                entity_type, entity_id, limit=limit
            )

    @staticmethod
    def compute_diff(
        old_dict: dict[str, Any], new_dict: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        """Compute field-level diff between two dictionaries.

        Args:
            old_dict: The original values.
            new_dict: The updated values.

        Returns:
            Dict of changed fields: {field_name: {"old": old_val, "new": new_val}}
        """
        diff: dict[str, dict[str, Any]] = {}
        all_keys = set(old_dict.keys()) | set(new_dict.keys())

        for key in all_keys:
            old_val = old_dict.get(key)
            new_val = new_dict.get(key)
            if old_val != new_val:
                diff[key] = {"old": old_val, "new": new_val}

        return diff
