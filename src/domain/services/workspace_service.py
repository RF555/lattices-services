"""Workspace service layer with business logic."""

import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import ClassVar, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from core.exceptions import (
    AlreadyAMemberError,
    InsufficientPermissionsError,
    LastOwnerError,
    LastWorkspaceError,
    NotAMemberError,
    WorkspaceNotFoundError,
    WorkspaceSlugTakenError,
)
from domain.entities.activity import Actions
from domain.entities.notification import NotificationTypes
from domain.entities.workspace import (
    Workspace,
    WorkspaceMember,
    WorkspaceRole,
    has_permission,
)
from domain.repositories.unit_of_work import IUnitOfWork
from domain.services.activity_service import ActivityService
from domain.services.notification_service import NotificationService


class WorkspaceService:
    """Service layer for Workspace business logic."""

    # In-memory cache of user IDs known to have at least one workspace.
    # Avoids a DB round-trip on every authenticated request for the 99.9%
    # case where the user already has workspaces.
    _provisioned_users: ClassVar[set[UUID]] = set()

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        activity_service: Optional["ActivityService"] = None,
        notification_service: Optional["NotificationService"] = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._activity = activity_service
        self._notification = notification_service

    @classmethod
    def clear_provisioned_cache(cls) -> None:
        """Clear the provisioned-users cache. Intended for testing."""
        cls._provisioned_users.clear()

    async def get_all_for_user(self, user_id: UUID) -> list[Workspace]:
        """Get all workspaces a user is a member of."""
        async with self._uow_factory() as uow:
            return await uow.workspaces.get_all_for_user(user_id)  # type: ignore[no-any-return]

    async def get_by_id(self, workspace_id: UUID, user_id: UUID) -> Workspace:
        """Get a workspace by ID, verifying user membership."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            member = await uow.workspaces.get_member(workspace_id, user_id)
            if not member:
                raise NotAMemberError(str(workspace_id))

            return workspace

    async def create(
        self,
        user_id: UUID,
        name: str,
        description: str | None = None,
    ) -> Workspace:
        """Create a new workspace and add the creator as Owner."""
        async with self._uow_factory() as uow:
            slug = self._generate_slug(name)

            # Ensure slug uniqueness
            existing = await uow.workspaces.get_by_slug(slug)
            if existing:
                slug = f"{slug}-{str(user_id)[:8]}"
                existing = await uow.workspaces.get_by_slug(slug)
                if existing:
                    raise WorkspaceSlugTakenError(slug)

            workspace = Workspace(
                name=name,
                slug=slug,
                description=description,
                created_by=user_id,
            )

            created = await uow.workspaces.create(workspace)

            # Add creator as Owner
            owner_member = WorkspaceMember(
                workspace_id=created.id,
                user_id=user_id,
                role=WorkspaceRole.OWNER,
            )
            await uow.workspaces.add_member(owner_member)

            await uow.commit()
            return created

    async def ensure_personal_workspace(self, user_id: UUID) -> Workspace | None:
        """Auto-create a "Personal" workspace if the user has none.

        Idempotent: returns None if the user already has workspaces.
        Handles race conditions from concurrent requests via IntegrityError catch.
        Uses an in-memory cache to skip the DB check for known-provisioned users.
        """
        logger = logging.getLogger(__name__)

        # Fast path: skip DB query for users already known to have workspaces
        if user_id in self._provisioned_users:
            return None

        async with self._uow_factory() as uow:
            existing = await uow.workspaces.get_all_for_user(user_id)
            if existing:
                self._provisioned_users.add(user_id)
                return None

            slug = f"personal-{str(user_id)[:8]}"

            # Handle slug collision by extending to 12 chars
            taken = await uow.workspaces.get_by_slug(slug)
            if taken:
                slug = f"personal-{str(user_id)[:12]}"

            workspace = Workspace(
                name="Personal",
                slug=slug,
                description=None,
                created_by=user_id,
            )

            try:
                created = await uow.workspaces.create(workspace)

                owner_member = WorkspaceMember(
                    workspace_id=created.id,
                    user_id=user_id,
                    role=WorkspaceRole.OWNER,
                )
                await uow.workspaces.add_member(owner_member)

                await uow.commit()
                self._provisioned_users.add(user_id)
                logger.info("Auto-created personal workspace for user %s", user_id)
                return created
            except IntegrityError as exc:
                await uow.rollback()
                # Only swallow unique-constraint violations (race condition).
                # Re-raise anything else (NOT NULL, FK, etc.) to avoid masking bugs.
                orig = str(exc.orig).lower() if exc.orig else ""
                if "unique" in orig or "duplicate" in orig:
                    self._provisioned_users.add(user_id)
                    logger.debug(
                        "Personal workspace already created (race condition) for user %s",
                        user_id,
                    )
                    return None
                raise

    async def update(
        self,
        workspace_id: UUID,
        user_id: UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> Workspace:
        """Update a workspace. Requires Admin+ role."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.ADMIN)

            old_state = {"name": workspace.name, "description": workspace.description}

            if name is not None:
                workspace.name = name
            if description is not None:
                workspace.description = description

            workspace.updated_at = datetime.utcnow()
            updated = await uow.workspaces.update(workspace)

            if self._activity:
                new_state = {"name": updated.name, "description": updated.description}
                changes = ActivityService.compute_diff(old_state, new_state)
                if changes:
                    await self._activity.log(
                        uow=uow,
                        workspace_id=workspace_id,
                        actor_id=user_id,
                        action=Actions.WORKSPACE_UPDATED,
                        entity_type="workspace",
                        entity_id=workspace_id,
                        changes=changes,
                    )

            await uow.commit()
            return updated

    async def delete(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Delete a workspace. Requires Owner role."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.OWNER)

            # Prevent deleting user's last workspace
            workspace_count = await uow.workspaces.count_user_workspaces(user_id)
            if workspace_count <= 1:
                raise LastWorkspaceError()

            deleted = await uow.workspaces.delete(workspace_id)
            await uow.commit()
            return deleted  # type: ignore[no-any-return]

    async def get_members(self, workspace_id: UUID, user_id: UUID) -> list[WorkspaceMember]:
        """Get all members of a workspace. Requires membership."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.VIEWER)

            return await uow.workspaces.get_members(workspace_id)  # type: ignore[no-any-return]

    async def add_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        target_user_id: UUID,
        role: WorkspaceRole = WorkspaceRole.MEMBER,
        actor_name: str | None = None,
    ) -> WorkspaceMember:
        """Add a member to a workspace. Requires Admin+ role.

        Cannot assign Owner role directly (use transfer_ownership instead).
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.ADMIN)

            if role == WorkspaceRole.OWNER:
                raise InsufficientPermissionsError("owner (use transfer_ownership)")

            # Check if target is already a member
            existing = await uow.workspaces.get_member(workspace_id, target_user_id)
            if existing:
                raise AlreadyAMemberError(str(target_user_id))

            member = WorkspaceMember(
                workspace_id=workspace_id,
                user_id=target_user_id,
                role=role,
                invited_by=user_id,
            )

            added = await uow.workspaces.add_member(member)

            if self._activity:
                await self._activity.log(
                    uow=uow,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    action=Actions.MEMBER_ADDED,
                    entity_type="member",
                    entity_id=target_user_id,
                    metadata={"role": role.name.lower()},
                )

            if self._notification:
                await self._notification.notify(
                    uow=uow,
                    type_name=NotificationTypes.MEMBER_ADDED,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    entity_type="workspace",
                    entity_id=workspace_id,
                    recipient_ids=[target_user_id],
                    metadata={
                        "actor_name": actor_name or "",
                        "workspace_name": workspace.name,
                    },
                )

            await uow.commit()
            return added

    async def update_member_role(
        self,
        workspace_id: UUID,
        user_id: UUID,
        target_user_id: UUID,
        role: WorkspaceRole,
        actor_name: str | None = None,
    ) -> WorkspaceMember:
        """Update a member's role. Requires Admin+ role.

        Cannot change own role. Cannot change Owner role (use transfer_ownership).
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.ADMIN)

            # Cannot change own role
            if user_id == target_user_id:
                raise InsufficientPermissionsError("cannot change own role")

            # Cannot assign or change to/from Owner
            target_member = await uow.workspaces.get_member(workspace_id, target_user_id)
            if not target_member:
                raise NotAMemberError(str(workspace_id))

            if target_member.role == WorkspaceRole.OWNER:
                raise InsufficientPermissionsError("owner (use transfer_ownership)")
            if role == WorkspaceRole.OWNER:
                raise InsufficientPermissionsError("owner (use transfer_ownership)")

            old_role = target_member.role.name.lower()
            updated = await uow.workspaces.update_member_role(workspace_id, target_user_id, role)

            if self._activity:
                await self._activity.log(
                    uow=uow,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    action=Actions.MEMBER_ROLE_CHANGED,
                    entity_type="member",
                    entity_id=target_user_id,
                    changes={"role": {"old": old_role, "new": role.name.lower()}},
                )

            if self._notification:
                await self._notification.notify(
                    uow=uow,
                    type_name=NotificationTypes.MEMBER_ROLE_CHANGED,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    entity_type="workspace",
                    entity_id=workspace_id,
                    recipient_ids=[target_user_id],
                    metadata={
                        "workspace_name": workspace.name,
                        "old_role": old_role,
                        "new_role": role.name.lower(),
                    },
                )

            await uow.commit()
            return updated

    async def remove_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        target_user_id: UUID,
    ) -> bool:
        """Remove a member from a workspace.

        - Admins can remove Members/Viewers
        - Owners can remove anyone except themselves
        - Members can remove themselves (leave)
        - Must prevent removing last Owner
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            actor_member = await uow.workspaces.get_member(workspace_id, user_id)
            if not actor_member:
                raise NotAMemberError(str(workspace_id))

            target_member = await uow.workspaces.get_member(workspace_id, target_user_id)
            if not target_member:
                raise NotAMemberError(str(workspace_id))

            is_self_leave = user_id == target_user_id

            if is_self_leave:
                # Prevent leaving last workspace
                workspace_count = await uow.workspaces.count_user_workspaces(target_user_id)
                if workspace_count <= 1:
                    raise LastWorkspaceError()

                # Prevent last owner from leaving
                if target_member.role == WorkspaceRole.OWNER:
                    owner_count = await uow.workspaces.count_owners(workspace_id)
                    if owner_count <= 1:
                        raise LastOwnerError()
            else:
                # Check actor has sufficient permissions to remove target
                if not has_permission(actor_member.role, WorkspaceRole.ADMIN):
                    raise InsufficientPermissionsError("admin")
                # Admins cannot remove other Admins or Owners
                if (
                    has_permission(target_member.role, actor_member.role)
                    and actor_member.role != WorkspaceRole.OWNER
                ):
                    raise InsufficientPermissionsError("owner")

            removed = await uow.workspaces.remove_member(workspace_id, target_user_id)

            if self._activity:
                action = Actions.MEMBER_LEFT if is_self_leave else Actions.MEMBER_REMOVED
                await self._activity.log(
                    uow=uow,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    action=action,
                    entity_type="member",
                    entity_id=target_user_id,
                    metadata={"role": target_member.role.name.lower()},
                )

            # Notify the removed user (not for self-leave)
            if not is_self_leave and self._notification:
                await self._notification.notify(
                    uow=uow,
                    type_name=NotificationTypes.MEMBER_REMOVED,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    entity_type="workspace",
                    entity_id=workspace_id,
                    recipient_ids=[target_user_id],
                    metadata={"workspace_name": workspace.name},
                )

            await uow.commit()
            return removed  # type: ignore[no-any-return]

    async def transfer_ownership(
        self,
        workspace_id: UUID,
        current_owner_id: UUID,
        new_owner_id: UUID,
    ) -> None:
        """Transfer workspace ownership. Current user must be Owner."""
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, current_owner_id, WorkspaceRole.OWNER)

            new_owner_member = await uow.workspaces.get_member(workspace_id, new_owner_id)
            if not new_owner_member:
                raise NotAMemberError(str(workspace_id))

            # Demote current owner to Admin, promote new owner to Owner
            await uow.workspaces.update_member_role(
                workspace_id, current_owner_id, WorkspaceRole.ADMIN
            )
            await uow.workspaces.update_member_role(workspace_id, new_owner_id, WorkspaceRole.OWNER)

            if self._activity:
                await self._activity.log(
                    uow=uow,
                    workspace_id=workspace_id,
                    actor_id=current_owner_id,
                    action=Actions.MEMBER_OWNERSHIP_TRANSFERRED,
                    entity_type="member",
                    entity_id=new_owner_id,
                    changes={
                        "previous_owner": {"old": str(current_owner_id), "new": "admin"},
                        "new_owner": {"old": str(new_owner_id), "new": "owner"},
                    },
                )

            await uow.commit()

    async def check_permission(
        self, workspace_id: UUID, user_id: UUID, required_role: WorkspaceRole
    ) -> bool:
        """Check if user has at least the required role in workspace.

        Returns True if permission is met, False otherwise.
        Does NOT raise exceptions (use _require_role for that).
        """
        async with self._uow_factory() as uow:
            member = await uow.workspaces.get_member(workspace_id, user_id)
            if not member:
                return False
            return has_permission(member.role, required_role)  # type: ignore[no-any-return]

    async def get_user_role(self, workspace_id: UUID, user_id: UUID) -> WorkspaceRole | None:
        """Get a user's role in a workspace, or None if not a member."""
        async with self._uow_factory() as uow:
            member = await uow.workspaces.get_member(workspace_id, user_id)
            return member.role if member else None

    # --- Internal helpers ---

    async def _require_role(
        self,
        uow: IUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        required_role: WorkspaceRole,
    ) -> WorkspaceMember:
        """Verify the user has at least the required role. Raises on failure."""
        member = await uow.workspaces.get_member(workspace_id, user_id)
        if not member:
            raise NotAMemberError(str(workspace_id))
        if not has_permission(member.role, required_role):
            raise InsufficientPermissionsError(required_role.name.lower())
        return member

    @staticmethod
    def _generate_slug(name: str) -> str:
        """Generate a URL-friendly slug from a workspace name."""
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        slug = re.sub(r"-+", "-", slug)
        slug = slug.strip("-")
        return slug[:100] if slug else "workspace"
