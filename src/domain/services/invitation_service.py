"""Invitation service layer with business logic."""

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from core.exceptions import (
    AlreadyAMemberError,
    DuplicateInvitationError,
    InsufficientPermissionsError,
    InvitationAlreadyAcceptedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    NotAMemberError,
    WorkspaceNotFoundError,
)
from domain.entities.invitation import (
    INVITATION_EXPIRY_DAYS,
    Invitation,
    InvitationStatus,
)
from domain.entities.notification import NotificationTypes
from domain.entities.workspace import WorkspaceMember, WorkspaceRole, has_permission
from domain.repositories.unit_of_work import IUnitOfWork
from domain.services.notification_service import NotificationService


class InvitationService:
    """Service layer for workspace invitation business logic."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        notification_service: Optional["NotificationService"] = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._notification = notification_service

    async def create_invitation(
        self,
        workspace_id: UUID,
        user_id: UUID,
        email: str,
        role: str = "member",
    ) -> tuple[Invitation, str]:
        """Create a workspace invitation.

        Args:
            workspace_id: The workspace to invite to.
            user_id: The user creating the invitation (must be Admin+).
            email: The email address to invite.
            role: The role to assign on acceptance.

        Returns:
            Tuple of (Invitation, raw_token). The raw_token is only available
            at creation time and should be shared with the invitee.

        Raises:
            WorkspaceNotFoundError: If workspace does not exist.
            InsufficientPermissionsError: If user is not Admin+.
            DuplicateInvitationError: If a pending invitation already exists.
            AlreadyAMemberError: If the email belongs to an existing member.
        """
        async with self._uow_factory() as uow:
            # Verify workspace exists
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            # Verify inviter has Admin+ role
            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.ADMIN)

            # Check for existing pending invitation
            existing = await uow.invitations.get_pending_for_workspace_email(workspace_id, email)
            if existing:
                raise DuplicateInvitationError(email)

            # Generate secure token
            raw_token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(raw_token)

            invitation = Invitation(
                workspace_id=workspace_id,
                email=email.lower().strip(),
                role=role,
                token_hash=token_hash,
                invited_by=user_id,
                expires_at=datetime.utcnow() + timedelta(days=INVITATION_EXPIRY_DAYS),
            )

            created = await uow.invitations.create(invitation)
            await uow.commit()

            return created, raw_token

    async def accept_invitation(
        self,
        token: str,
        user_id: UUID,
        user_email: str,
        actor_name: str | None = None,
    ) -> WorkspaceMember:
        """Accept a workspace invitation using the raw token.

        Args:
            token: The raw invitation token.
            user_id: The user accepting the invitation.
            user_email: The email of the accepting user (for verification).

        Returns:
            The new WorkspaceMember created from the invitation.

        Raises:
            InvitationNotFoundError: If token does not match any invitation.
            InvitationExpiredError: If the invitation has expired.
            InvitationAlreadyAcceptedError: If already accepted.
            InvitationEmailMismatchError: If user email doesn't match.
            AlreadyAMemberError: If user is already a workspace member.
        """
        async with self._uow_factory() as uow:
            token_hash = self._hash_token(token)
            invitation = await uow.invitations.get_by_token_hash(token_hash)

            if not invitation:
                raise InvitationNotFoundError()

            return await self._process_acceptance(invitation, user_id, user_email, actor_name, uow)

    async def accept_by_id(
        self,
        invitation_id: UUID,
        user_id: UUID,
        user_email: str,
        actor_name: str | None = None,
    ) -> WorkspaceMember:
        """Accept a workspace invitation by its ID (for in-app banner flow).

        Args:
            invitation_id: The invitation UUID.
            user_id: The user accepting the invitation.
            user_email: The email of the accepting user (for verification).
            actor_name: Optional display name of the accepting user.

        Returns:
            The new WorkspaceMember created from the invitation.

        Raises:
            InvitationNotFoundError: If invitation ID does not exist.
            InvitationExpiredError: If the invitation has expired.
            InvitationAlreadyAcceptedError: If already accepted.
            InvitationEmailMismatchError: If user email doesn't match.
            AlreadyAMemberError: If user is already a workspace member.
        """
        async with self._uow_factory() as uow:
            invitation = await uow.invitations.get_by_id(invitation_id)

            if not invitation:
                raise InvitationNotFoundError()

            return await self._process_acceptance(invitation, user_id, user_email, actor_name, uow)

    async def _process_acceptance(
        self,
        invitation: Invitation,
        user_id: UUID,
        user_email: str,
        actor_name: str | None,
        uow: IUnitOfWork,
    ) -> WorkspaceMember:
        """Shared validation and acceptance logic for both token and ID flows."""
        # Check status
        if invitation.status == InvitationStatus.ACCEPTED:
            raise InvitationAlreadyAcceptedError()
        if invitation.status != InvitationStatus.PENDING:
            raise InvitationNotFoundError()

        # Check expiry
        if invitation.is_expired:
            await uow.invitations.update_status(invitation.id, InvitationStatus.EXPIRED)
            await uow.commit()
            raise InvitationExpiredError()

        # Verify email matches
        if user_email.lower().strip() != invitation.email.lower().strip():
            raise InvitationEmailMismatchError()

        # Check if user is already a member
        existing_member = await uow.workspaces.get_member(invitation.workspace_id, user_id)
        if existing_member:
            # Mark invitation as accepted anyway to prevent reuse
            await uow.invitations.update_status(invitation.id, InvitationStatus.ACCEPTED)
            await uow.commit()
            raise AlreadyAMemberError(str(user_id))

        # Map role string to enum
        role_map = {
            "admin": WorkspaceRole.ADMIN,
            "member": WorkspaceRole.MEMBER,
            "viewer": WorkspaceRole.VIEWER,
        }
        role = role_map.get(invitation.role, WorkspaceRole.MEMBER)

        # Add user as workspace member
        member = WorkspaceMember(
            workspace_id=invitation.workspace_id,
            user_id=user_id,
            role=role,
            invited_by=invitation.invited_by,
        )
        added = await uow.workspaces.add_member(member)

        # Mark invitation as accepted
        await uow.invitations.update_status(invitation.id, InvitationStatus.ACCEPTED)

        # Notify the inviter that the invitation was accepted
        if self._notification:
            workspace = await uow.workspaces.get(invitation.workspace_id)
            workspace_name = workspace.name if workspace else ""
            await self._notification.notify(
                uow=uow,
                type_name=NotificationTypes.INVITATION_ACCEPTED,
                workspace_id=invitation.workspace_id,
                actor_id=user_id,
                entity_type="invitation",
                entity_id=invitation.id,
                recipient_ids=[invitation.invited_by],
                metadata={
                    "actor_name": actor_name or user_email,
                    "workspace_name": workspace_name,
                },
            )

        await uow.commit()
        return added

    async def revoke_invitation(
        self,
        workspace_id: UUID,
        invitation_id: UUID,
        user_id: UUID,
    ) -> bool:
        """Revoke a pending invitation. Requires Admin+ role.

        Args:
            workspace_id: The workspace the invitation belongs to.
            invitation_id: The invitation to revoke.
            user_id: The user revoking (must be Admin+).

        Returns:
            True if successfully revoked.

        Raises:
            WorkspaceNotFoundError: If workspace does not exist.
            InsufficientPermissionsError: If user is not Admin+.
            InvitationNotFoundError: If invitation does not exist.
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.ADMIN)

            # Get all workspace invitations and find the matching one
            invitations = await uow.invitations.get_for_workspace(workspace_id)
            invitation = next((inv for inv in invitations if inv.id == invitation_id), None)

            if not invitation:
                raise InvitationNotFoundError(str(invitation_id))

            if invitation.status != InvitationStatus.PENDING:
                raise InvitationNotFoundError(str(invitation_id))

            await uow.invitations.update_status(invitation_id, InvitationStatus.REVOKED)
            await uow.commit()
            return True

    async def get_workspace_invitations(
        self,
        workspace_id: UUID,
        user_id: UUID,
    ) -> list[Invitation]:
        """Get all invitations for a workspace. Requires membership.

        Args:
            workspace_id: The workspace to list invitations for.
            user_id: The requesting user (must be a member).

        Returns:
            List of invitations for the workspace.
        """
        async with self._uow_factory() as uow:
            workspace = await uow.workspaces.get(workspace_id)
            if not workspace:
                raise WorkspaceNotFoundError(str(workspace_id))

            await self._require_role(uow, workspace_id, user_id, WorkspaceRole.VIEWER)

            return await uow.invitations.get_for_workspace(workspace_id)  # type: ignore[no-any-return]

    async def get_user_pending_invitations(self, email: str) -> list[Invitation]:
        """Get all pending invitations for an email address.

        Used to show pending invitations on login/dashboard.

        Args:
            email: The email address to check.

        Returns:
            List of pending (non-expired) invitations.
        """
        async with self._uow_factory() as uow:
            return await uow.invitations.get_pending_for_email(  # type: ignore[no-any-return]
                email.lower().strip()
            )

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
    def _hash_token(token: str) -> str:
        """Hash a raw invitation token using SHA-256."""
        return hashlib.sha256(token.encode()).hexdigest()
