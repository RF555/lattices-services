"""Unit tests for TagService."""

from uuid import UUID, uuid4

import pytest

from core.exceptions import (
    AppException,
    InsufficientPermissionsError,
    NotAMemberError,
    TagNotFoundError,
    TodoNotFoundError,
)
from domain.entities.tag import Tag
from domain.entities.todo import Todo
from domain.entities.workspace import WorkspaceMember, WorkspaceRole
from domain.services.tag_service import TagService
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> TagService:
    return TagService(lambda: uow)


# --- get_all_for_user ---


class TestGetAllForUser:
    @pytest.mark.asyncio
    async def test_returns_user_tags(self, service: TagService, uow: FakeUnitOfWork, user_id: UUID):
        tag = Tag(user_id=user_id, name="Bug")
        uow.tags.get_all_for_user.return_value = [tag]
        uow.tags.get_usage_counts_batch.return_value = {tag.id: 3}

        result = await service.get_all_for_user(user_id)

        assert len(result) == 1
        assert result[0].tag.name == "Bug"
        assert result[0].usage_count == 3

    @pytest.mark.asyncio
    async def test_returns_workspace_tags(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        tag = Tag(user_id=user_id, name="Feature", workspace_id=workspace_id)
        uow.tags.get_all_for_workspace.return_value = [tag]
        uow.tags.get_usage_counts_batch.return_value = {tag.id: 0}

        result = await service.get_all_for_user(user_id, workspace_id=workspace_id)

        assert len(result) == 1
        uow.tags.get_all_for_workspace.assert_called_once_with(workspace_id)


# --- create ---


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_tag_for_user(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.tags.get_by_name.return_value = None
        created_tag = Tag(user_id=user_id, name="New Tag")
        uow.tags.create.return_value = created_tag

        result = await service.create(user_id=user_id, name="New Tag")

        assert result.name == "New Tag"
        uow.tags.create.assert_called_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_creates_workspace_tag(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.tags.get_by_name_in_workspace.return_value = None
        created_tag = Tag(user_id=user_id, name="WS Tag", workspace_id=workspace_id)
        uow.tags.create.return_value = created_tag

        result = await service.create(user_id=user_id, name="WS Tag", workspace_id=workspace_id)

        assert result.workspace_id == workspace_id
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_duplicate(self, service: TagService, uow: FakeUnitOfWork, user_id: UUID):
        uow.tags.get_by_name.return_value = Tag(user_id=user_id, name="Existing")

        with pytest.raises(AppException) as exc_info:
            await service.create(user_id=user_id, name="Existing")

        assert exc_info.value.status_code == 409


# --- update ---


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_tag_name(self, service: TagService, uow: FakeUnitOfWork, user_id: UUID):
        tag = Tag(user_id=user_id, name="Old")
        uow.tags.get.return_value = tag
        uow.tags.get_by_name.return_value = None
        uow.tags.update.return_value = tag

        await service.update(tag.id, user_id, name="New")

        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found_for_wrong_user(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        other_user = uuid4()
        tag = Tag(user_id=other_user, name="Private")
        uow.tags.get.return_value = tag

        with pytest.raises(TagNotFoundError):
            await service.update(tag.id, user_id, name="Hack")

    @pytest.mark.asyncio
    async def test_raises_duplicate_on_rename(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        tag = Tag(user_id=user_id, name="Original")
        uow.tags.get.return_value = tag
        uow.tags.get_by_name.return_value = Tag(user_id=user_id, name="Taken")

        with pytest.raises(AppException) as exc_info:
            await service.update(tag.id, user_id, name="Taken")

        assert exc_info.value.status_code == 409


# --- delete ---


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_tag(self, service: TagService, uow: FakeUnitOfWork, user_id: UUID):
        tag = Tag(user_id=user_id, name="ToDelete")
        uow.tags.get.return_value = tag
        uow.tags.delete.return_value = True

        result = await service.delete(tag.id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_found(self, service: TagService, uow: FakeUnitOfWork, user_id: UUID):
        uow.tags.get.return_value = None

        with pytest.raises(TagNotFoundError):
            await service.delete(uuid4(), user_id)


# --- attach_to_todo / detach_from_todo ---


class TestAttachDetach:
    @pytest.mark.asyncio
    async def test_attach_tag_to_todo(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        tag = Tag(user_id=user_id, name="Priority")
        todo = Todo(user_id=user_id, title="Task")
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo

        await service.attach_to_todo(tag.id, todo.id, user_id)

        uow.tags.attach_to_todo.assert_called_once_with(tag.id, todo.id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_attach_raises_tag_not_found(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        uow.tags.get.return_value = None

        with pytest.raises(TagNotFoundError):
            await service.attach_to_todo(uuid4(), uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_detach_tag_from_todo(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID
    ):
        tag = Tag(user_id=user_id, name="Priority")
        todo = Todo(user_id=user_id, title="Task")
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo

        await service.detach_from_todo(tag.id, todo.id, user_id)

        uow.tags.detach_from_todo.assert_called_once_with(tag.id, todo.id)
        assert uow.committed


# --- get_tags_for_todos_batch ---


class TestBatch:
    @pytest.mark.asyncio
    async def test_empty_input_returns_empty(self, service: TagService, uow: FakeUnitOfWork):
        result = await service.get_tags_for_todos_batch([])

        assert result == {}
        uow.tags.get_for_todos_batch.assert_not_called()


# ---------------------------------------------------------------------------
# Workspace-scoped tests
# ---------------------------------------------------------------------------


class TestGetByIdWorkspace:
    """Tests for get_by_id when the tag belongs to a workspace."""

    @pytest.mark.asyncio
    async def test_should_return_tag_when_user_is_workspace_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="WS Tag", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )

        result = await service.get_by_id(tag.id, user_id)

        assert result.name == "WS Tag"
        uow.workspaces.get_member.assert_called_once_with(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_user_is_not_workspace_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="WS Tag", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = None

        with pytest.raises(TagNotFoundError):
            await service.get_by_id(tag.id, user_id)


class TestCreateWorkspace:
    """Tests for create when workspace_id is provided."""

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_user_not_in_workspace(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.create(user_id=user_id, name="Tag", workspace_id=workspace_id)

    @pytest.mark.asyncio
    async def test_should_raise_insufficient_permissions_when_viewer(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.create(user_id=user_id, name="Tag", workspace_id=workspace_id)

    @pytest.mark.asyncio
    async def test_should_raise_duplicate_when_name_exists_in_workspace(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.tags.get_by_name_in_workspace.return_value = Tag(
            user_id=user_id, name="Existing", workspace_id=workspace_id
        )

        with pytest.raises(AppException) as exc_info:
            await service.create(user_id=user_id, name="Existing", workspace_id=workspace_id)

        assert exc_info.value.status_code == 409


class TestUpdateWorkspace:
    """Tests for update when the tag belongs to a workspace."""

    @pytest.mark.asyncio
    async def test_should_update_workspace_tag_when_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="Old", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.tags.get_by_name_in_workspace.return_value = None
        uow.tags.update.return_value = tag

        await service.update(tag.id, user_id, name="New")

        assert uow.committed
        uow.tags.get_by_name_in_workspace.assert_called_once_with(workspace_id, "New")

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_non_member_updates(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="WS Tag", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.update(tag.id, user_id, name="Hacked")

    @pytest.mark.asyncio
    async def test_should_raise_duplicate_when_workspace_name_taken(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="Original", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.tags.get_by_name_in_workspace.return_value = Tag(
            user_id=uuid4(), name="Taken", workspace_id=workspace_id
        )

        with pytest.raises(AppException) as exc_info:
            await service.update(tag.id, user_id, name="Taken")

        assert exc_info.value.status_code == 409


class TestDeleteWorkspace:
    """Tests for delete when the tag belongs to a workspace."""

    @pytest.mark.asyncio
    async def test_should_delete_workspace_tag_when_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="WS Tag", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.tags.delete.return_value = True

        result = await service.delete(tag.id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_non_member_deletes(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="WS Tag", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.delete(tag.id, user_id)


class TestAttachDetachWorkspace:
    """Tests for attach_to_todo / detach_from_todo with workspace-scoped tags and todos."""

    @pytest.mark.asyncio
    async def test_attach_should_succeed_when_tag_and_todo_in_same_workspace(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="Feature", workspace_id=workspace_id)
        todo = Todo(user_id=uuid4(), title="Task", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        await service.attach_to_todo(tag.id, todo.id, user_id)

        uow.tags.attach_to_todo.assert_called_once_with(tag.id, todo.id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_attach_should_raise_when_tag_and_todo_in_different_workspaces(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        other_workspace = uuid4()
        tag = Tag(user_id=uuid4(), name="Feature", workspace_id=workspace_id)
        todo = Todo(user_id=uuid4(), title="Task", workspace_id=other_workspace)
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(TodoNotFoundError):
            await service.attach_to_todo(tag.id, todo.id, user_id)

    @pytest.mark.asyncio
    async def test_detach_should_succeed_when_workspace_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="Feature", workspace_id=workspace_id)
        todo = Todo(user_id=uuid4(), title="Task", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        await service.detach_from_todo(tag.id, todo.id, user_id)

        uow.tags.detach_from_todo.assert_called_once_with(tag.id, todo.id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_detach_should_raise_when_non_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        tag = Tag(user_id=uuid4(), name="Feature", workspace_id=workspace_id)
        todo = Todo(user_id=uuid4(), title="Task", workspace_id=workspace_id)
        uow.tags.get.return_value = tag
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.detach_from_todo(tag.id, todo.id, user_id)


class TestGetTagsForTodoWorkspace:
    """Tests for get_tags_for_todo when the todo belongs to a workspace."""

    @pytest.mark.asyncio
    async def test_should_return_tags_when_user_is_workspace_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        todo = Todo(user_id=uuid4(), title="WS Task", workspace_id=workspace_id)
        expected_tags = [Tag(user_id=uuid4(), name="Bug", workspace_id=workspace_id)]
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.tags.get_for_todo.return_value = expected_tags

        result = await service.get_tags_for_todo(todo.id, user_id)

        assert result == expected_tags
        uow.workspaces.get_member.assert_called_once_with(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_should_raise_not_found_when_non_member(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        todo = Todo(user_id=uuid4(), title="WS Task", workspace_id=workspace_id)
        uow.todos.get.return_value = todo
        uow.workspaces.get_member.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.get_tags_for_todo(todo.id, user_id)


class TestGetAllForUserWorkspace:
    """Tests for get_all_for_user workspace-scoped branch -- non-member rejection."""

    @pytest.mark.asyncio
    async def test_should_raise_not_a_member_when_non_member_queries_workspace(
        self, service: TagService, uow: FakeUnitOfWork, user_id: UUID, workspace_id: UUID
    ):
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_all_for_user(user_id, workspace_id=workspace_id)
