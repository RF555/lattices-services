"""Unit tests for InvitationService."""

import hashlib
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from core.exceptions import (
    AlreadyAMemberError,
    DuplicateInvitationError,
    InsufficientPermissionsError,
    InvitationAlreadyAcceptedError,
    InvitationEmailMismatchError,
    InvitationExpiredError,
    InvitationNotFoundError,
    WorkspaceNotFoundError,
)
from domain.entities.invitation import Invitation, InvitationStatus
from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole
from domain.services.invitation_service import InvitationService
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> InvitationService:
    return InvitationService(lambda: uow)


@pytest.fixture
def workspace(workspace_id: UUID, user_id: UUID) -> Workspace:
    return Workspace(id=workspace_id, name="Test WS", slug="test-ws", created_by=user_id)


@pytest.fixture
def admin_member(workspace_id: UUID, user_id: UUID) -> WorkspaceMember:
    return WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN)


# --- create_invitation ---


class TestCreateInvitation:
    @pytest.mark.asyncio
    async def test_creates_invitation_and_returns_token(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        admin_member: WorkspaceMember,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = admin_member
        uow.invitations.get_pending_for_workspace_email.return_value = None
        uow.workspaces.get_members.return_value = []

        async def capture_create(inv: Any) -> Any:
            return inv

        uow.invitations.create.side_effect = capture_create

        result, raw_token = await service.create_invitation(
            workspace_id=workspace_id, user_id=user_id, email="new@example.com", role="member"
        )

        assert result.email == "new@example.com"
        assert result.workspace_id == workspace_id
        assert raw_token is not None
        assert len(raw_token) > 0
        assert uow.committed

    @pytest.mark.asyncio
    async def test_token_hash_is_sha256(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        admin_member: WorkspaceMember,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = admin_member
        uow.invitations.get_pending_for_workspace_email.return_value = None
        uow.workspaces.get_members.return_value = []

        captured = None

        async def capture_create(inv: Any) -> Any:
            nonlocal captured
            captured = inv
            return inv

        uow.invitations.create.side_effect = capture_create

        _, raw_token = await service.create_invitation(
            workspace_id=workspace_id, user_id=user_id, email="test@example.com"
        )

        expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        assert captured is not None
        assert captured.token_hash == expected_hash

    @pytest.mark.asyncio
    async def test_raises_workspace_not_found(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.create_invitation(
                workspace_id=workspace_id, user_id=user_id, email="t@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_insufficient_permissions_for_member(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.create_invitation(
                workspace_id=workspace_id, user_id=user_id, email="t@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_duplicate_for_existing_pending(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        admin_member: WorkspaceMember,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        existing = Invitation(
            workspace_id=workspace_id,
            email="dup@example.com",
            role="member",
            token_hash="x",
            invited_by=user_id,
        )
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = admin_member
        uow.invitations.get_pending_for_workspace_email.return_value = existing

        with pytest.raises(DuplicateInvitationError):
            await service.create_invitation(
                workspace_id=workspace_id, user_id=user_id, email="dup@example.com"
            )


# --- accept_invitation ---


class TestAcceptInvitation:
    @pytest.mark.asyncio
    async def test_accepts_and_creates_member(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        raw_token = "valid_token_123"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        inviter_id = uuid4()
        invitation = Invitation(
            workspace_id=workspace_id,
            email="new@example.com",
            role="member",
            token_hash=token_hash,
            invited_by=inviter_id,
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )

        uow.invitations.get_by_token_hash.return_value = invitation
        uow.workspaces.get_member.return_value = None  # not yet a member
        new_member = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.workspaces.add_member.return_value = new_member

        result = await service.accept_invitation(
            token=raw_token, user_id=user_id, user_email="new@example.com"
        )

        assert result.workspace_id == workspace_id
        assert result.user_id == user_id
        uow.workspaces.add_member.assert_called_once()
        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.ACCEPTED
        )
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found_for_bad_token(
        self, service: InvitationService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        uow.invitations.get_by_token_hash.return_value = None

        with pytest.raises(InvitationNotFoundError):
            await service.accept_invitation(
                token="bad", user_id=user_id, user_email="t@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_already_accepted(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        raw_token = "tok"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invitation = Invitation(
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash=token_hash,
            invited_by=uuid4(),
            status=InvitationStatus.ACCEPTED,
        )
        uow.invitations.get_by_token_hash.return_value = invitation

        with pytest.raises(InvitationAlreadyAcceptedError):
            await service.accept_invitation(
                token=raw_token, user_id=user_id, user_email="t@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_expired(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        raw_token = "tok"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invitation = Invitation(
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash=token_hash,
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        uow.invitations.get_by_token_hash.return_value = invitation

        with pytest.raises(InvitationExpiredError):
            await service.accept_invitation(
                token=raw_token, user_id=user_id, user_email="t@example.com"
            )

        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.EXPIRED
        )

    @pytest.mark.asyncio
    async def test_raises_email_mismatch(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        raw_token = "tok"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invitation = Invitation(
            workspace_id=workspace_id,
            email="invited@example.com",
            role="member",
            token_hash=token_hash,
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        uow.invitations.get_by_token_hash.return_value = invitation

        with pytest.raises(InvitationEmailMismatchError):
            await service.accept_invitation(
                token=raw_token, user_id=user_id, user_email="other@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_already_a_member(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        raw_token = "tok"
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        invitation = Invitation(
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash=token_hash,
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        uow.invitations.get_by_token_hash.return_value = invitation
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(AlreadyAMemberError):
            await service.accept_invitation(
                token=raw_token, user_id=user_id, user_email="t@example.com"
            )

        # Marks accepted to prevent reuse
        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.ACCEPTED
        )


# --- accept_by_id ---


class TestAcceptById:
    @pytest.mark.asyncio
    async def test_accepts_by_id_and_creates_member(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        invitation_id = uuid4()
        inviter_id = uuid4()
        invitation = Invitation(
            id=invitation_id,
            workspace_id=workspace_id,
            email="new@example.com",
            role="member",
            token_hash="irrelevant",
            invited_by=inviter_id,
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )

        uow.invitations.get_by_id.return_value = invitation
        uow.workspaces.get_member.return_value = None  # not yet a member
        new_member = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.workspaces.add_member.return_value = new_member

        result = await service.accept_by_id(
            invitation_id=invitation_id, user_id=user_id, user_email="new@example.com"
        )

        assert result.workspace_id == workspace_id
        assert result.user_id == user_id
        uow.workspaces.add_member.assert_called_once()
        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.ACCEPTED
        )
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found_for_nonexistent_id(
        self, service: InvitationService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        uow.invitations.get_by_id.return_value = None

        with pytest.raises(InvitationNotFoundError):
            await service.accept_by_id(
                invitation_id=uuid4(), user_id=user_id, user_email="t@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_expired_by_id(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        invitation_id = uuid4()
        invitation = Invitation(
            id=invitation_id,
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash="irrelevant",
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() - timedelta(days=1),
        )
        uow.invitations.get_by_id.return_value = invitation

        with pytest.raises(InvitationExpiredError):
            await service.accept_by_id(
                invitation_id=invitation_id, user_id=user_id, user_email="t@example.com"
            )

        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.EXPIRED
        )

    @pytest.mark.asyncio
    async def test_raises_email_mismatch_by_id(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        invitation_id = uuid4()
        invitation = Invitation(
            id=invitation_id,
            workspace_id=workspace_id,
            email="invited@example.com",
            role="member",
            token_hash="irrelevant",
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        uow.invitations.get_by_id.return_value = invitation

        with pytest.raises(InvitationEmailMismatchError):
            await service.accept_by_id(
                invitation_id=invitation_id, user_id=user_id, user_email="other@example.com"
            )

    @pytest.mark.asyncio
    async def test_raises_already_a_member_by_id(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        invitation_id = uuid4()
        invitation = Invitation(
            id=invitation_id,
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash="irrelevant",
            invited_by=uuid4(),
            status=InvitationStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
        uow.invitations.get_by_id.return_value = invitation
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(AlreadyAMemberError):
            await service.accept_by_id(
                invitation_id=invitation_id, user_id=user_id, user_email="t@example.com"
            )

        uow.invitations.update_status.assert_called_once_with(
            invitation.id, InvitationStatus.ACCEPTED
        )


# --- revoke_invitation ---


class TestRevokeInvitation:
    @pytest.mark.asyncio
    async def test_revokes_pending(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        admin_member: WorkspaceMember,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        invitation_id = uuid4()
        invitation = Invitation(
            id=invitation_id,
            workspace_id=workspace_id,
            email="t@example.com",
            role="member",
            token_hash="hash",
            invited_by=user_id,
            status=InvitationStatus.PENDING,
        )
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = admin_member
        uow.invitations.get_for_workspace.return_value = [invitation]

        result = await service.revoke_invitation(
            workspace_id=workspace_id, invitation_id=invitation_id, user_id=user_id
        )

        assert result is True
        uow.invitations.update_status.assert_called_once_with(
            invitation_id, InvitationStatus.REVOKED
        )
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        admin_member: WorkspaceMember,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = admin_member
        uow.invitations.get_for_workspace.return_value = []

        with pytest.raises(InvitationNotFoundError):
            await service.revoke_invitation(
                workspace_id=workspace_id, invitation_id=uuid4(), user_id=user_id
            )

    @pytest.mark.asyncio
    async def test_raises_insufficient_permissions(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.revoke_invitation(
                workspace_id=workspace_id, invitation_id=uuid4(), user_id=user_id
            )


# --- get_workspace_invitations ---


class TestGetWorkspaceInvitations:
    @pytest.mark.asyncio
    async def test_returns_invitations(
        self,
        service: InvitationService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ) -> None:
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        inv1 = Invitation(
            workspace_id=workspace_id,
            email="a@example.com",
            role="member",
            token_hash="h1",
            invited_by=user_id,
        )
        inv2 = Invitation(
            workspace_id=workspace_id,
            email="b@example.com",
            role="admin",
            token_hash="h2",
            invited_by=user_id,
        )
        uow.invitations.get_for_workspace.return_value = [inv1, inv2]

        result = await service.get_workspace_invitations(workspace_id=workspace_id, user_id=user_id)

        assert len(result) == 2
        uow.invitations.get_for_workspace.assert_called_once_with(workspace_id)
