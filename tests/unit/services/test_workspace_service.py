"""Unit tests for WorkspaceService."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

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
from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole
from domain.services.workspace_service import WorkspaceService
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> WorkspaceService:
    return WorkspaceService(lambda: uow)


@pytest.fixture
def mock_activity_service() -> AsyncMock:
    """A mock ActivityService with a log() method and compute_diff static method."""
    mock = AsyncMock()
    mock.log = AsyncMock()
    # compute_diff is a static method that returns real diffs; we import the real one
    from domain.services.activity_service import ActivityService

    mock.compute_diff = ActivityService.compute_diff
    return mock


@pytest.fixture
def mock_notification_service() -> AsyncMock:
    """A mock NotificationService with a notify() method."""
    mock = AsyncMock()
    mock.notify = AsyncMock()
    return mock


@pytest.fixture
def service_with_activity(
    uow: FakeUnitOfWork,
    mock_activity_service: AsyncMock,
) -> WorkspaceService:
    """WorkspaceService wired with a mock ActivityService (no notifications)."""
    return WorkspaceService(lambda: uow, activity_service=mock_activity_service)


@pytest.fixture
def service_with_notifications(
    uow: FakeUnitOfWork,
    mock_activity_service: AsyncMock,
    mock_notification_service: AsyncMock,
) -> WorkspaceService:
    """WorkspaceService wired with both mock ActivityService and NotificationService."""
    return WorkspaceService(
        lambda: uow,
        activity_service=mock_activity_service,
        notification_service=mock_notification_service,
    )


@pytest.fixture
def sample_workspace(workspace_id: UUID, user_id: UUID) -> Workspace:
    return Workspace(
        id=workspace_id,
        name="Test Workspace",
        slug="test-workspace",
        description="A test workspace",
        created_by=user_id,
    )


# --- get_all_for_user ---


class TestGetAllForUser:
    @pytest.mark.asyncio
    async def test_returns_workspaces(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        ws1 = Workspace(name="WS1", slug="ws-1", created_by=user_id)
        ws2 = Workspace(name="WS2", slug="ws-2", created_by=user_id)
        uow.workspaces.get_all_for_user.return_value = [ws1, ws2]

        result = await service.get_all_for_user(user_id)

        assert len(result) == 2
        uow.workspaces.get_all_for_user.assert_called_once_with(user_id)


# --- get_by_id ---


class TestGetById:
    @pytest.mark.asyncio
    async def test_returns_workspace_when_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        result = await service.get_by_id(workspace_id, user_id)
        assert result.id == workspace_id

    @pytest.mark.asyncio
    async def test_raises_not_found_when_missing(
        self, service: WorkspaceService, uow: FakeUnitOfWork, workspace_id: UUID, user_id: UUID
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.get_by_id(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_not_a_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_by_id(workspace_id, user_id)


# --- create ---


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_workspace_with_owner(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.workspaces.get_by_slug.return_value = None
        created = Workspace(name="New WS", slug="new-ws", created_by=user_id)
        uow.workspaces.create.return_value = created
        uow.workspaces.add_member.return_value = WorkspaceMember(
            workspace_id=created.id, user_id=user_id, role=WorkspaceRole.OWNER
        )

        result = await service.create(user_id=user_id, name="New WS")

        assert result.name == "New WS"
        uow.workspaces.create.assert_called_once()
        uow.workspaces.add_member.assert_called_once()
        add_call = uow.workspaces.add_member.call_args[0][0]
        assert add_call.role == WorkspaceRole.OWNER
        assert uow.committed

    @pytest.mark.asyncio
    async def test_slug_generation(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.workspaces.get_by_slug.return_value = None
        uow.workspaces.create.return_value = Workspace(
            name="Test Workspace!", slug="test-workspace", created_by=user_id
        )

        await service.create(user_id=user_id, name="Test Workspace!")

        create_call = uow.workspaces.create.call_args[0][0]
        assert create_call.slug == "test-workspace"

    @pytest.mark.asyncio
    async def test_raises_slug_taken_on_collision(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        existing = Workspace(name="Existing", slug="test-workspace", created_by=user_id)
        uow.workspaces.get_by_slug.return_value = existing

        with pytest.raises(WorkspaceSlugTakenError):
            await service.create(user_id=user_id, name="Test Workspace")


# --- update ---


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_name_and_description(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        updated = Workspace(
            id=workspace_id,
            name="Updated",
            slug="test-workspace",
            description="Updated desc",
            created_by=user_id,
        )
        uow.workspaces.update.return_value = updated

        result = await service.update(
            workspace_id=workspace_id, user_id=user_id, name="Updated", description="Updated desc"
        )

        assert result.name == "Updated"
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found(
        self, service: WorkspaceService, uow: FakeUnitOfWork, workspace_id: UUID, user_id: UUID
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.update(workspace_id=workspace_id, user_id=user_id, name="New")

    @pytest.mark.asyncio
    async def test_raises_insufficient_permissions_for_viewer(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.update(workspace_id=workspace_id, user_id=user_id, name="New")


# --- delete ---


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_workspace_as_owner(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.delete.return_value = True

        result = await service.delete(workspace_id=workspace_id, user_id=user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_insufficient_permissions_for_admin(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.delete(workspace_id=workspace_id, user_id=user_id)


# --- add_member ---


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,  # target not yet a member
        ]
        new_member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
            invited_by=user_id,
        )
        uow.workspaces.add_member.return_value = new_member

        result = await service.add_member(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
        )

        assert result.user_id == target_user_id
        assert result.role == WorkspaceRole.MEMBER
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_already_a_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]

        with pytest.raises(AlreadyAMemberError):
            await service.add_member(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=target_user_id,
                role=WorkspaceRole.MEMBER,
            )

    @pytest.mark.asyncio
    async def test_rejects_owner_role_assignment(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.add_member(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=uuid4(),
                role=WorkspaceRole.OWNER,
            )


# --- update_member_role ---


class TestUpdateMemberRole:
    @pytest.mark.asyncio
    async def test_updates_role(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.update_member_role.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.ADMIN
        )

        result = await service.update_member_role(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.ADMIN,
        )

        assert result.role == WorkspaceRole.ADMIN
        assert uow.committed

    @pytest.mark.asyncio
    async def test_cannot_change_own_role(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.update_member_role(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=user_id,
                role=WorkspaceRole.VIEWER,
            )

    @pytest.mark.asyncio
    async def test_rejects_owner_role_change(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]

        with pytest.raises(InsufficientPermissionsError):
            await service.update_member_role(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=target_user_id,
                role=WorkspaceRole.OWNER,
            )


# --- remove_member ---


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_admin_removes_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.remove_member.return_value = True

        result = await service.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
        )

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_self_leave(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
        ]
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.remove_member.return_value = True

        result = await service.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=user_id
        )

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_last_owner_cannot_leave(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
        ]
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.count_owners.return_value = 1

        with pytest.raises(LastOwnerError):
            await service.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=user_id
            )

    @pytest.mark.asyncio
    async def test_member_cannot_remove_other_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]

        with pytest.raises(InsufficientPermissionsError):
            await service.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
            )


# --- transfer_ownership ---


class TestTransferOwnership:
    @pytest.mark.asyncio
    async def test_transfers_ownership(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        new_owner_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=new_owner_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.update_member_role.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=new_owner_id, role=WorkspaceRole.OWNER
            ),
        ]

        await service.transfer_ownership(
            workspace_id=workspace_id,
            current_owner_id=user_id,
            new_owner_id=new_owner_id,
        )

        assert uow.workspaces.update_member_role.call_count == 2
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_for_non_owner(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.transfer_ownership(
                workspace_id=workspace_id,
                current_owner_id=user_id,
                new_owner_id=uuid4(),
            )

    @pytest.mark.asyncio
    async def test_raises_for_non_member_target(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
            None,  # new owner not a member
        ]

        with pytest.raises(NotAMemberError):
            await service.transfer_ownership(
                workspace_id=workspace_id,
                current_owner_id=user_id,
                new_owner_id=uuid4(),
            )


# --- check_permission ---


class TestCheckPermission:
    @pytest.mark.asyncio
    async def test_returns_true_when_sufficient(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        result = await service.check_permission(workspace_id, user_id, WorkspaceRole.MEMBER)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_insufficient(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )

        result = await service.check_permission(workspace_id, user_id, WorkspaceRole.ADMIN)
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_not_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = None

        result = await service.check_permission(workspace_id, user_id, WorkspaceRole.VIEWER)
        assert result is False


# --- get_user_role ---


class TestGetUserRole:
    @pytest.mark.asyncio
    async def test_should_return_role_when_user_is_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )

        result = await service.get_user_role(workspace_id, user_id)

        assert result == WorkspaceRole.ADMIN
        uow.workspaces.get_member.assert_called_once_with(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_should_return_none_when_user_is_not_member(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = None

        result = await service.get_user_role(workspace_id, user_id)

        assert result is None


# --- get_members ---


class TestGetMembers:
    @pytest.mark.asyncio
    async def test_should_return_members_when_user_is_viewer(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        members = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER),
            WorkspaceMember(workspace_id=workspace_id, user_id=uuid4(), role=WorkspaceRole.ADMIN),
        ]
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.workspaces.get_members.return_value = members

        result = await service.get_members(workspace_id, user_id)

        assert len(result) == 2
        uow.workspaces.get_members.assert_called_once_with(workspace_id)

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_workspace_missing(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.get_members(workspace_id, user_id)


# --- Activity logging on update ---


class TestUpdateActivityLogging:
    @pytest.mark.asyncio
    async def test_should_log_activity_when_workspace_name_changes(
        self,
        service_with_activity: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        updated = Workspace(
            id=workspace_id,
            name="New Name",
            slug="test-workspace",
            description=sample_workspace.description,
            created_by=user_id,
        )
        uow.workspaces.update.return_value = updated

        await service_with_activity.update(
            workspace_id=workspace_id, user_id=user_id, name="New Name"
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.WORKSPACE_UPDATED
        assert call_kwargs["workspace_id"] == workspace_id
        assert call_kwargs["actor_id"] == user_id
        assert call_kwargs["entity_type"] == "workspace"
        assert "name" in call_kwargs["changes"]

    @pytest.mark.asyncio
    async def test_should_not_log_activity_when_no_fields_change(
        self,
        service_with_activity: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        # Return a workspace with identical name and description (no change)
        unchanged = Workspace(
            id=workspace_id,
            name=sample_workspace.name,
            slug="test-workspace",
            description=sample_workspace.description,
            created_by=user_id,
        )
        uow.workspaces.update.return_value = unchanged

        await service_with_activity.update(workspace_id=workspace_id, user_id=user_id)

        mock_activity_service.log.assert_not_called()


# --- Activity logging and notification on add_member ---


class TestAddMemberActivityAndNotification:
    @pytest.mark.asyncio
    async def test_should_log_activity_when_member_added(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,  # target not yet a member
        ]
        new_member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
            invited_by=user_id,
        )
        uow.workspaces.add_member.return_value = new_member

        await service_with_notifications.add_member(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.MEMBER_ADDED
        assert call_kwargs["entity_type"] == "member"
        assert call_kwargs["entity_id"] == target_user_id
        assert call_kwargs["metadata"] == {"role": "member"}

    @pytest.mark.asyncio
    async def test_should_notify_target_user_when_member_added(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_notification_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,
        ]
        new_member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
            invited_by=user_id,
        )
        uow.workspaces.add_member.return_value = new_member

        await service_with_notifications.add_member(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
            actor_name="Alice",
        )

        mock_notification_service.notify.assert_called_once()
        call_kwargs = mock_notification_service.notify.call_args[1]
        assert call_kwargs["type_name"] == NotificationTypes.MEMBER_ADDED
        assert call_kwargs["workspace_id"] == workspace_id
        assert call_kwargs["recipient_ids"] == [target_user_id]
        assert call_kwargs["metadata"]["actor_name"] == "Alice"
        assert call_kwargs["metadata"]["workspace_name"] == sample_workspace.name

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_workspace_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service_with_notifications.add_member(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=uuid4(),
            )


# --- Activity logging and notification on update_member_role ---


class TestUpdateMemberRoleActivityAndNotification:
    @pytest.mark.asyncio
    async def test_should_log_activity_when_role_changed(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.update_member_role.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.ADMIN
        )

        await service_with_notifications.update_member_role(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.ADMIN,
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.MEMBER_ROLE_CHANGED
        assert call_kwargs["changes"] == {"role": {"old": "member", "new": "admin"}}

    @pytest.mark.asyncio
    async def test_should_notify_target_when_role_changed(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_notification_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.VIEWER
            ),
        ]
        uow.workspaces.update_member_role.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
        )

        await service_with_notifications.update_member_role(
            workspace_id=workspace_id,
            user_id=user_id,
            target_user_id=target_user_id,
            role=WorkspaceRole.MEMBER,
        )

        mock_notification_service.notify.assert_called_once()
        call_kwargs = mock_notification_service.notify.call_args[1]
        assert call_kwargs["type_name"] == NotificationTypes.MEMBER_ROLE_CHANGED
        assert call_kwargs["recipient_ids"] == [target_user_id]
        assert call_kwargs["metadata"]["old_role"] == "viewer"
        assert call_kwargs["metadata"]["new_role"] == "member"
        assert call_kwargs["metadata"]["workspace_name"] == sample_workspace.name

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_workspace_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service_with_notifications.update_member_role(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=uuid4(),
                role=WorkspaceRole.MEMBER,
            )

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_target_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,  # target not a member
        ]

        with pytest.raises(NotAMemberError):
            await service_with_notifications.update_member_role(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=target_user_id,
                role=WorkspaceRole.MEMBER,
            )

    @pytest.mark.asyncio
    async def test_should_raise_when_target_is_owner(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.OWNER
            ),
        ]

        with pytest.raises(InsufficientPermissionsError):
            await service_with_notifications.update_member_role(
                workspace_id=workspace_id,
                user_id=user_id,
                target_user_id=target_user_id,
                role=WorkspaceRole.MEMBER,
            )


# --- Activity logging and notification on remove_member ---


class TestRemoveMemberActivityAndNotification:
    @pytest.mark.asyncio
    async def test_should_log_activity_with_removed_action_when_admin_removes_member(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.remove_member.return_value = True

        await service_with_notifications.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.MEMBER_REMOVED
        assert call_kwargs["entity_id"] == target_user_id
        assert call_kwargs["metadata"] == {"role": "member"}

    @pytest.mark.asyncio
    async def test_should_log_activity_with_left_action_when_self_leave(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
        mock_notification_service: AsyncMock,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
        ]
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.remove_member.return_value = True

        await service_with_notifications.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=user_id
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.MEMBER_LEFT

        # Self-leave should NOT trigger notification
        mock_notification_service.notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_notify_removed_user(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_notification_service: AsyncMock,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.remove_member.return_value = True

        await service_with_notifications.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
        )

        mock_notification_service.notify.assert_called_once()
        call_kwargs = mock_notification_service.notify.call_args[1]
        assert call_kwargs["type_name"] == NotificationTypes.MEMBER_REMOVED
        assert call_kwargs["recipient_ids"] == [target_user_id]
        assert call_kwargs["metadata"]["workspace_name"] == sample_workspace.name

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_workspace_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service_with_notifications.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=uuid4()
            )

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_actor_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            None,  # actor not a member
        ]

        with pytest.raises(NotAMemberError):
            await service_with_notifications.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=uuid4()
            )

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_target_missing(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,  # target not a member
        ]

        with pytest.raises(NotAMemberError):
            await service_with_notifications.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
            )

    @pytest.mark.asyncio
    async def test_should_raise_when_admin_tries_to_remove_another_admin(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        """Admin cannot remove another Admin -- only Owner can remove Admins."""
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.ADMIN
            ),
        ]

        with pytest.raises(InsufficientPermissionsError):
            await service_with_notifications.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
            )

    @pytest.mark.asyncio
    async def test_should_allow_owner_to_remove_admin(
        self,
        service_with_notifications: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        """Owner should be able to remove an Admin member."""
        target_user_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=target_user_id, role=WorkspaceRole.ADMIN
            ),
        ]
        uow.workspaces.remove_member.return_value = True

        result = await service_with_notifications.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=target_user_id
        )

        assert result is True
        assert uow.committed


# --- Activity logging on transfer_ownership ---


class TestTransferOwnershipActivityLogging:
    @pytest.mark.asyncio
    async def test_should_log_activity_on_ownership_transfer(
        self,
        service_with_activity: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
        mock_activity_service: AsyncMock,
    ):
        new_owner_id = uuid4()
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=new_owner_id, role=WorkspaceRole.MEMBER
            ),
        ]
        uow.workspaces.update_member_role.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(
                workspace_id=workspace_id, user_id=new_owner_id, role=WorkspaceRole.OWNER
            ),
        ]

        await service_with_activity.transfer_ownership(
            workspace_id=workspace_id,
            current_owner_id=user_id,
            new_owner_id=new_owner_id,
        )

        mock_activity_service.log.assert_called_once()
        call_kwargs = mock_activity_service.log.call_args[1]
        assert call_kwargs["action"] == Actions.MEMBER_OWNERSHIP_TRANSFERRED
        assert call_kwargs["entity_id"] == new_owner_id
        assert "previous_owner" in call_kwargs["changes"]
        assert "new_owner" in call_kwargs["changes"]
        assert uow.committed

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_workspace_missing(
        self,
        service_with_activity: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service_with_activity.transfer_ownership(
                workspace_id=workspace_id,
                current_owner_id=user_id,
                new_owner_id=uuid4(),
            )


# --- ensure_personal_workspace ---


class TestEnsurePersonalWorkspace:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        """Clear the provisioned-users cache before each test."""
        WorkspaceService.clear_provisioned_cache()
        yield
        WorkspaceService.clear_provisioned_cache()

    @pytest.mark.asyncio
    async def test_creates_workspace_when_user_has_none(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.workspaces.get_all_for_user.return_value = []
        uow.workspaces.get_by_slug.return_value = None
        slug = f"personal-{str(user_id)[:8]}"
        created = Workspace(name="Personal", slug=slug, created_by=user_id)
        uow.workspaces.create.return_value = created
        uow.workspaces.add_member.return_value = WorkspaceMember(
            workspace_id=created.id, user_id=user_id, role=WorkspaceRole.OWNER
        )

        result = await service.ensure_personal_workspace(user_id)

        assert result is not None
        assert result.name == "Personal"
        assert result.slug.startswith("personal-")
        uow.workspaces.create.assert_called_once()
        uow.workspaces.add_member.assert_called_once()
        add_call = uow.workspaces.add_member.call_args[0][0]
        assert add_call.role == WorkspaceRole.OWNER
        assert uow.committed

    @pytest.mark.asyncio
    async def test_noop_when_user_has_workspaces(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        existing_ws = Workspace(name="Existing", slug="existing", created_by=user_id)
        uow.workspaces.get_all_for_user.return_value = [existing_ws]

        result = await service.ensure_personal_workspace(user_id)

        assert result is None
        uow.workspaces.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_slug_collision(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.workspaces.get_all_for_user.return_value = []
        # First slug is taken, second is not
        existing = Workspace(name="Other", slug=f"personal-{str(user_id)[:8]}", created_by=uuid4())
        uow.workspaces.get_by_slug.return_value = existing
        created = Workspace(
            name="Personal", slug=f"personal-{str(user_id)[:12]}", created_by=user_id
        )
        uow.workspaces.create.return_value = created
        uow.workspaces.add_member.return_value = WorkspaceMember(
            workspace_id=created.id, user_id=user_id, role=WorkspaceRole.OWNER
        )

        result = await service.ensure_personal_workspace(user_id)

        assert result is not None
        create_call = uow.workspaces.create.call_args[0][0]
        assert create_call.slug == f"personal-{str(user_id)[:12]}"
        assert uow.committed

    @pytest.mark.asyncio
    async def test_cache_skips_db_on_second_call(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """After confirming a user has workspaces, subsequent calls skip the DB."""
        existing_ws = Workspace(name="Existing", slug="existing", created_by=user_id)
        uow.workspaces.get_all_for_user.return_value = [existing_ws]

        # First call hits DB
        await service.ensure_personal_workspace(user_id)
        assert uow.workspaces.get_all_for_user.call_count == 1

        # Second call skips DB entirely (cache hit)
        await service.ensure_personal_workspace(user_id)
        assert uow.workspaces.get_all_for_user.call_count == 1  # still 1

    @pytest.mark.asyncio
    async def test_cache_populated_after_creation(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """After creating a workspace, the user is cached as provisioned."""
        uow.workspaces.get_all_for_user.return_value = []
        uow.workspaces.get_by_slug.return_value = None
        slug = f"personal-{str(user_id)[:8]}"
        created = Workspace(name="Personal", slug=slug, created_by=user_id)
        uow.workspaces.create.return_value = created
        uow.workspaces.add_member.return_value = WorkspaceMember(
            workspace_id=created.id, user_id=user_id, role=WorkspaceRole.OWNER
        )

        await service.ensure_personal_workspace(user_id)

        # Second call should be a cache hit — no additional DB calls
        await service.ensure_personal_workspace(user_id)
        assert uow.workspaces.get_all_for_user.call_count == 1

    @pytest.mark.asyncio
    async def test_non_unique_integrity_error_is_reraised(
        self, service: WorkspaceService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """IntegrityErrors that are NOT unique-constraint violations must be re-raised."""
        from sqlalchemy.exc import IntegrityError

        uow.workspaces.get_all_for_user.return_value = []
        uow.workspaces.get_by_slug.return_value = None
        uow.workspaces.create.side_effect = IntegrityError(
            "INSERT ...", {}, Exception("NOT NULL constraint failed: workspaces.name")
        )

        with pytest.raises(IntegrityError):
            await service.ensure_personal_workspace(user_id)


# --- Last workspace guards ---


class TestLastWorkspaceGuard:
    @pytest.mark.asyncio
    async def test_delete_raises_when_last_workspace(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
        uow.workspaces.count_user_workspaces.return_value = 1

        with pytest.raises(LastWorkspaceError):
            await service.delete(workspace_id=workspace_id, user_id=user_id)

    @pytest.mark.asyncio
    async def test_delete_succeeds_when_user_has_other_workspaces(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.OWNER
        )
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.delete.return_value = True

        result = await service.delete(workspace_id=workspace_id, user_id=user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_self_leave_raises_when_last_workspace(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
        ]
        uow.workspaces.count_user_workspaces.return_value = 1

        with pytest.raises(LastWorkspaceError):
            await service.remove_member(
                workspace_id=workspace_id, user_id=user_id, target_user_id=user_id
            )

    @pytest.mark.asyncio
    async def test_self_leave_succeeds_when_user_has_other_workspaces(
        self,
        service: WorkspaceService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        sample_workspace: Workspace,
    ):
        uow.workspaces.get.return_value = sample_workspace
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER),
        ]
        uow.workspaces.count_user_workspaces.return_value = 2
        uow.workspaces.remove_member.return_value = True

        result = await service.remove_member(
            workspace_id=workspace_id, user_id=user_id, target_user_id=user_id
        )

        assert result is True
        assert uow.committed
