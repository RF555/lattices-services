"""Unit tests for ActivityService."""

from uuid import UUID, uuid4

import pytest

from core.exceptions import NotAMemberError, WorkspaceNotFoundError
from domain.entities.activity import ActivityLog
from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole
from domain.services.activity_service import ActivityService
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> ActivityService:
    return ActivityService(lambda: uow)


@pytest.fixture
def workspace(workspace_id: UUID, user_id: UUID) -> Workspace:
    return Workspace(id=workspace_id, name="Test WS", slug="test-ws", created_by=user_id)


# --- log ---


class TestLog:
    @pytest.mark.asyncio
    async def test_creates_activity_entry(
        self, uow: FakeUnitOfWork, workspace_id: UUID, user_id: UUID
    ):
        service = ActivityService(lambda: uow)
        entity_id = uuid4()
        expected = ActivityLog(
            workspace_id=workspace_id,
            actor_id=user_id,
            action="todo.created",
            entity_type="todo",
            entity_id=entity_id,
        )
        uow.activities.create.return_value = expected

        result = await service.log(
            uow=uow,
            workspace_id=workspace_id,
            actor_id=user_id,
            action="todo.created",
            entity_type="todo",
            entity_id=entity_id,
        )

        assert result.action == "todo.created"
        uow.activities.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_changes_and_metadata(
        self, uow: FakeUnitOfWork, workspace_id: UUID, user_id: UUID
    ):
        service = ActivityService(lambda: uow)
        entity_id = uuid4()
        changes = {"title": {"old": "Old", "new": "New"}}
        metadata = {"role": "admin"}

        uow.activities.create.return_value = ActivityLog(
            workspace_id=workspace_id,
            actor_id=user_id,
            action="member.role_changed",
            entity_type="member",
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )

        await service.log(
            uow=uow,
            workspace_id=workspace_id,
            actor_id=user_id,
            action="member.role_changed",
            entity_type="member",
            entity_id=entity_id,
            changes=changes,
            metadata=metadata,
        )

        call_arg = uow.activities.create.call_args[0][0]
        assert call_arg.changes == changes
        assert call_arg.metadata == metadata


# --- get_workspace_activity ---


class TestGetWorkspaceActivity:
    @pytest.mark.asyncio
    async def test_returns_activity_feed(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        log_entry = ActivityLog(
            workspace_id=workspace_id,
            actor_id=user_id,
            action="todo.created",
            entity_type="todo",
            entity_id=uuid4(),
        )
        uow.activities.get_for_workspace.return_value = [log_entry]

        result = await service.get_workspace_activity(workspace_id, user_id)

        assert len(result) == 1
        assert result[0].action == "todo.created"

    @pytest.mark.asyncio
    async def test_raises_workspace_not_found(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.get_workspace_activity(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_not_a_member(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_workspace_activity(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_passes_pagination_params(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.activities.get_for_workspace.return_value = []

        await service.get_workspace_activity(workspace_id, user_id, limit=10, offset=5)

        uow.activities.get_for_workspace.assert_called_once_with(workspace_id, limit=10, offset=5)


# --- get_entity_history ---


class TestGetEntityHistory:
    @pytest.mark.asyncio
    async def test_returns_entity_history(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        entity_id = uuid4()
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.activities.get_for_entity.return_value = []

        result = await service.get_entity_history(workspace_id, user_id, "todo", entity_id)

        assert result == []
        uow.activities.get_for_entity.assert_called_once_with("todo", entity_id, limit=50)

    @pytest.mark.asyncio
    async def test_raises_workspace_not_found(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.get_entity_history(workspace_id, user_id, "todo", uuid4())

    @pytest.mark.asyncio
    async def test_raises_not_a_member(
        self,
        service: ActivityService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_entity_history(workspace_id, user_id, "todo", uuid4())


# --- compute_diff ---


class TestComputeDiff:
    def test_detects_changed_fields(self):
        old = {"name": "Old Name", "color": "blue"}
        new = {"name": "New Name", "color": "blue"}

        diff = ActivityService.compute_diff(old, new)

        assert "name" in diff
        assert diff["name"]["old"] == "Old Name"
        assert diff["name"]["new"] == "New Name"
        assert "color" not in diff

    def test_returns_empty_for_identical(self):
        data = {"name": "Same", "color": "red"}
        diff = ActivityService.compute_diff(data, data)
        assert diff == {}
