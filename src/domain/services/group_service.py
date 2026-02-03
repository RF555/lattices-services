"""Group service layer with business logic."""

from typing import Callable, List, Optional

from uuid import UUID

from core.exceptions import (
    AlreadyAGroupMemberError,
    GroupMemberNotFoundError,
    GroupNotFoundError,
    InsufficientPermissionsError,
    NotAMemberError,
    WorkspaceNotFoundError,
)
from domain.entities.group import Group, GroupMember, GroupRole
from domain.entities.notification import NotificationTypes
from domain.entities.workspace import WorkspaceRole, has_permission
from domain.repositories.unit_of_work import IUnitOfWork
from domain.services.notification_service import NotificationService


class GroupService:
    """Service layer for workspace group management."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        notification_service: Optional["NotificationService"] = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._notification = notification_service

    async def get_for_workspace(
        self, workspace_id: UUID, user_id: UUID
    ) -> List[Group]:
        """Get all groups in a workspace. Requires membership."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_workspace_role(
                uow, workspace_id, user_id, WorkspaceRole.VIEWER
            )

            return await uow.groups.get_for_workspace(workspace_id)

    async def get_by_id(
        self, workspace_id: UUID, group_id: UUID, user_id: UUID
    ) -> Group:
        """Get a group by ID. Requires workspace membership."""
        async with self._uow_factory() as uow:
            await self._require_workspace_role(
                uow, workspace_id, user_id, WorkspaceRole.VIEWER
            )

            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            return group

    async def create(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: str,
        description: Optional[str] = None,
    ) -> Group:
        """Create a group in a workspace. Requires Admin+ role."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_workspace_role(
                uow, workspace_id, user_id, WorkspaceRole.ADMIN
            )

            group = Group(
                workspace_id=workspace_id,
                name=name,
                description=description,
                created_by=user_id,
            )

            created = await uow.groups.create(group)

            # Add creator as group admin
            admin_member = GroupMember(
                group_id=created.id,
                user_id=user_id,
                role=GroupRole.ADMIN,
            )
            await uow.groups.add_member(admin_member)

            await uow.commit()
            return created

    async def update(
        self,
        workspace_id: UUID,
        group_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Group:
        """Update a group. Requires workspace Admin+ or group Admin."""
        async with self._uow_factory() as uow:
            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            # Check permission: workspace admin+ OR group admin
            await self._require_group_or_workspace_admin(
                uow, workspace_id, group_id, user_id
            )

            if name is not None:
                group.name = name
            if description is not None:
                group.description = description

            updated = await uow.groups.update(group)
            await uow.commit()
            return updated

    async def delete(
        self, workspace_id: UUID, group_id: UUID, user_id: UUID
    ) -> bool:
        """Delete a group. Requires workspace Admin+ role."""
        async with self._uow_factory() as uow:
            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            await self._require_workspace_role(
                uow, workspace_id, user_id, WorkspaceRole.ADMIN
            )

            deleted = await uow.groups.delete(group_id)
            await uow.commit()
            return deleted

    async def get_members(
        self, workspace_id: UUID, group_id: UUID, user_id: UUID
    ) -> List[GroupMember]:
        """Get all members of a group. Requires workspace membership."""
        async with self._uow_factory() as uow:
            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            await self._require_workspace_role(
                uow, workspace_id, user_id, WorkspaceRole.VIEWER
            )

            return await uow.groups.get_members(group_id)

    async def add_member(
        self,
        workspace_id: UUID,
        group_id: UUID,
        user_id: UUID,
        target_user_id: UUID,
        role: GroupRole = GroupRole.MEMBER,
        actor_name: Optional[str] = None,
    ) -> GroupMember:
        """Add a member to a group. Requires workspace Admin+ or group Admin."""
        async with self._uow_factory() as uow:
            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            await self._require_group_or_workspace_admin(
                uow, workspace_id, group_id, user_id
            )

            # Verify target is a workspace member
            ws_member = await uow.workspaces.get_member(workspace_id, target_user_id)
            if not ws_member:
                raise NotAMemberError(str(workspace_id))

            # Check if already a group member
            existing = await uow.groups.get_member(group_id, target_user_id)
            if existing:
                raise AlreadyAGroupMemberError(str(target_user_id))

            member = GroupMember(
                group_id=group_id,
                user_id=target_user_id,
                role=role,
            )

            added = await uow.groups.add_member(member)

            if self._notification:
                await self._notification.notify(
                    uow=uow,
                    type_name=NotificationTypes.GROUP_MEMBER_ADDED,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    entity_type="group",
                    entity_id=group_id,
                    recipient_ids=[target_user_id],
                    metadata={
                        "actor_name": actor_name or "",
                        "group_name": group.name,
                    },
                )

            await uow.commit()
            return added

    async def remove_member(
        self,
        workspace_id: UUID,
        group_id: UUID,
        user_id: UUID,
        target_user_id: UUID,
    ) -> bool:
        """Remove a member from a group.

        Workspace Admin+ or group Admin can remove anyone.
        Members can remove themselves.
        """
        async with self._uow_factory() as uow:
            group = await uow.groups.get(group_id)
            if not group or group.workspace_id != workspace_id:
                raise GroupNotFoundError(str(group_id))

            target_member = await uow.groups.get_member(group_id, target_user_id)
            if not target_member:
                raise GroupMemberNotFoundError(str(target_user_id))

            is_self = user_id == target_user_id
            if not is_self:
                await self._require_group_or_workspace_admin(
                    uow, workspace_id, group_id, user_id
                )

            removed = await uow.groups.remove_member(group_id, target_user_id)
            await uow.commit()
            return removed

    # --- Internal helpers ---

    async def _require_workspace_role(
        self,
        uow: IUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        required_role: WorkspaceRole,
    ) -> None:
        """Verify the user has at least the required workspace role."""
        member = await uow.workspaces.get_member(workspace_id, user_id)
        if not member:
            raise NotAMemberError(str(workspace_id))
        if not has_permission(member.role, required_role):
            raise InsufficientPermissionsError(required_role.name.lower())

    async def _require_group_or_workspace_admin(
        self,
        uow: IUnitOfWork,
        workspace_id: UUID,
        group_id: UUID,
        user_id: UUID,
    ) -> None:
        """Verify user is workspace Admin+ OR group Admin."""
        # Check workspace role first
        ws_member = await uow.workspaces.get_member(workspace_id, user_id)
        if not ws_member:
            raise NotAMemberError(str(workspace_id))

        if has_permission(ws_member.role, WorkspaceRole.ADMIN):
            return  # Workspace admin+ can manage any group

        # Check group role
        group_member = await uow.groups.get_member(group_id, user_id)
        if group_member and group_member.role == GroupRole.ADMIN:
            return  # Group admin can manage

        raise InsufficientPermissionsError("admin")
