"""Unit tests for Todo service layer."""

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from core.exceptions import (
    AppException,
    InsufficientPermissionsError,
    NotAMemberError,
    TodoNotFoundError,
)
from domain.entities.activity import Actions
from domain.entities.notification import NotificationTypes
from domain.entities.todo import Todo
from domain.entities.workspace import WorkspaceMember, WorkspaceRole
from domain.services.activity_service import ActivityService
from domain.services.notification_service import NotificationService
from domain.services.todo_service import TodoService

# FakeUnitOfWork is provided by the shared conftest at tests/unit/conftest.py.
# Import it here only for type-hint usage in fixtures/tests.
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> TodoService:
    """Create service with fake UoW (no activity/notification services)."""
    return TodoService(lambda: uow)


@pytest.fixture
def sample_todo(user_id: UUID) -> Todo:
    return Todo(
        id=uuid4(),
        user_id=user_id,
        title="Sample Task",
        description="Sample description",
        position=0,
    )


class TestTodoServiceGetAll:
    @pytest.mark.asyncio
    async def test_returns_all_user_todos(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test get_all_for_user returns all todos for user."""
        todos = [
            Todo(user_id=user_id, title="Task 1"),
            Todo(user_id=user_id, title="Task 2"),
        ]
        uow.todos.get_all_for_user.return_value = todos

        result = await service.get_all_for_user(user_id)

        assert len(result) == 2
        uow.todos.get_all_for_user.assert_called_once_with(user_id)


class TestTodoServiceGetById:
    @pytest.mark.asyncio
    async def test_returns_todo_when_found(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ) -> None:
        """Test get_by_id returns todo when found."""
        uow.todos.get.return_value = sample_todo

        result = await service.get_by_id(sample_todo.id, user_id)

        assert result.id == sample_todo.id

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test get_by_id raises TodoNotFoundError when not found."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_raises_when_wrong_user(
        self, service: TodoService, uow: FakeUnitOfWork, sample_todo: Todo
    ) -> None:
        """Test get_by_id raises when todo belongs to different user."""
        uow.todos.get.return_value = sample_todo

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(sample_todo.id, uuid4())  # Different user


class TestTodoServiceCreate:
    @pytest.mark.asyncio
    async def test_creates_root_todo(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test creating a root-level todo."""
        expected = Todo(user_id=user_id, title="New Task")
        uow.todos.get_root_todos.return_value = []
        uow.todos.create.return_value = expected

        await service.create(user_id=user_id, title="New Task")

        uow.todos.create.assert_called_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_creates_child_todo(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ) -> None:
        """Test creating a child todo."""
        parent = sample_todo
        uow.todos.get.return_value = parent
        uow.todos.get_children.return_value = []
        uow.todos.create.return_value = Todo(user_id=user_id, title="Child", parent_id=parent.id)

        await service.create(user_id=user_id, title="Child", parent_id=parent.id)

        assert uow.committed

    @pytest.mark.asyncio
    async def test_create_with_invalid_parent_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test creating todo with non-existent parent raises error."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.create(user_id=user_id, title="Task", parent_id=uuid4())


class TestTodoServiceUpdate:
    @pytest.mark.asyncio
    async def test_updates_title(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ) -> None:
        """Test updating todo title."""
        uow.todos.get.return_value = sample_todo
        uow.todos.update.return_value = sample_todo

        await service.update(todo_id=sample_todo.id, user_id=user_id, title="Updated")

        uow.todos.update.assert_called_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_completes_todo(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ) -> None:
        """Test completing a todo."""
        uow.todos.get.return_value = sample_todo
        uow.todos.update.return_value = sample_todo

        await service.update(todo_id=sample_todo.id, user_id=user_id, is_completed=True)

        assert sample_todo.is_completed
        assert sample_todo.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_not_found_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test updating non-existent todo raises."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.update(todo_id=uuid4(), user_id=user_id, title="Updated")


class TestTodoServiceChildCounts:
    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_input(
        self, service: TodoService, uow: FakeUnitOfWork
    ) -> None:
        """Empty list returns {} without touching repo."""
        result = await service.get_child_counts_batch([])

        assert result == {}
        uow.todos.get_child_counts_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_delegates_to_repo(self, service: TodoService, uow: FakeUnitOfWork) -> None:
        """Verifies delegation to uow.todos.get_child_counts_batch."""
        todo_id = uuid4()
        uow.todos.get_child_counts_batch.return_value = {
            todo_id: (3, 1),
        }

        result = await service.get_child_counts_batch([todo_id])

        assert result == {todo_id: (3, 1)}
        uow.todos.get_child_counts_batch.assert_called_once_with([todo_id])


class TestTodoServiceDelete:
    @pytest.mark.asyncio
    async def test_deletes_todo(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ) -> None:
        """Test deleting a todo."""
        uow.todos.get.return_value = sample_todo
        uow.todos.delete.return_value = True

        result = await service.delete(sample_todo.id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Test deleting non-existent todo raises."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.delete(uuid4(), user_id)


class TestTodoServiceCycleDetection:
    """Tests for _would_create_cycle and circular parent rejection."""

    @pytest.mark.asyncio
    async def test_detects_direct_cycle(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Moving a parent under its own child creates a direct cycle."""
        parent = Todo(user_id=user_id, title="Parent")
        child = Todo(user_id=user_id, title="Child", parent_id=parent.id)

        # When checking if parent can become child of child:
        # get(child.id) -> child (has parent_id == parent.id)
        # get(parent.id) -> parent (parent_id matches todo_id => cycle)
        def mock_get(todo_id: Any) -> Todo | None:
            if todo_id == child.id:
                return child
            if todo_id == parent.id:
                return parent
            return None

        uow.todos.get = AsyncMock(side_effect=mock_get)

        # Try to update parent to have child as its parent -> cycle
        uow.todos.update = AsyncMock(return_value=parent)
        # Simulate: parent is found, user owns it, new parent_id = child.id
        parent_copy = Todo(user_id=user_id, title="Parent")
        parent_copy.id = parent.id
        uow.todos.get.side_effect = None

        # First call: get(parent.id) -> parent (for ownership check)
        # Then for cycle detection: get(child.id) -> child, get(parent.id) -> cycle!
        call_count = 0

        async def get_side_effect(tid: Any) -> Todo | None:
            nonlocal call_count
            call_count += 1
            if tid == parent.id:
                return parent
            if tid == child.id:
                return child
            return None

        uow.todos.get = AsyncMock(side_effect=get_side_effect)

        with pytest.raises(AppException) as exc_info:
            await service.update(todo_id=parent.id, user_id=user_id, parent_id=child.id)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_detects_indirect_cycle(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Moving A under C when C -> B -> A creates an indirect cycle."""
        a = Todo(user_id=user_id, title="A")
        b = Todo(user_id=user_id, title="B", parent_id=a.id)
        c = Todo(user_id=user_id, title="C", parent_id=b.id)

        async def get_side_effect(tid: Any) -> Todo | None:
            if tid == a.id:
                return a
            if tid == b.id:
                return b
            if tid == c.id:
                return c
            return None

        uow.todos.get = AsyncMock(side_effect=get_side_effect)

        # Try to move A under C -> C.parent=B, B.parent=A => cycle
        with pytest.raises(AppException) as exc_info:
            await service.update(todo_id=a.id, user_id=user_id, parent_id=c.id)

        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_no_cycle_for_valid_move(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Moving a todo to a non-descendant does not raise."""
        a = Todo(user_id=user_id, title="A")
        b = Todo(user_id=user_id, title="B")  # no parent relationship with A

        async def get_side_effect(tid: Any) -> Todo | None:
            if tid == a.id:
                return a
            if tid == b.id:
                return b
            return None

        uow.todos.get = AsyncMock(side_effect=get_side_effect)
        uow.todos.update = AsyncMock(return_value=a)

        await service.update(todo_id=a.id, user_id=user_id, parent_id=b.id)

        assert uow.committed

    @pytest.mark.asyncio
    async def test_update_rejects_self_as_parent(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Setting a todo as its own parent is rejected."""
        todo = Todo(user_id=user_id, title="Self")

        uow.todos.get = AsyncMock(return_value=todo)

        with pytest.raises(AppException) as exc_info:
            await service.update(todo_id=todo.id, user_id=user_id, parent_id=todo.id)

        assert exc_info.value.status_code == 400


class TestTodoServiceWorkspaceScoped:
    """Tests for workspace-scoped todo operations."""

    # -- Helpers / fixtures --------------------------------------------------

    @pytest.fixture
    def ws_id(self) -> UUID:
        """A dedicated workspace ID for workspace-scoped tests."""
        return uuid4()

    @pytest.fixture
    def member(self, ws_id: UUID, user_id: UUID) -> WorkspaceMember:
        """A workspace member with MEMBER role."""
        return WorkspaceMember(workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.MEMBER)

    @pytest.fixture
    def viewer(self, ws_id: UUID, user_id: UUID) -> WorkspaceMember:
        """A workspace member with VIEWER role (read-only)."""
        return WorkspaceMember(workspace_id=ws_id, user_id=user_id, role=WorkspaceRole.VIEWER)

    @pytest.fixture
    def ws_todo(self, user_id: UUID, ws_id: UUID) -> Todo:
        """A todo that belongs to a workspace."""
        return Todo(
            id=uuid4(),
            user_id=user_id,
            workspace_id=ws_id,
            title="Workspace Task",
            description="WS description",
            position=0,
        )

    @pytest.fixture
    def activity_service(self) -> AsyncMock:
        """A mock ActivityService whose .log() is an AsyncMock."""
        return AsyncMock(spec=ActivityService)

    @pytest.fixture
    def notification_service(self) -> AsyncMock:
        """A mock NotificationService whose .notify() is an AsyncMock."""
        return AsyncMock(spec=NotificationService)

    @pytest.fixture
    def ws_service(
        self,
        uow: FakeUnitOfWork,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> TodoService:
        """TodoService wired with activity + notification services."""
        return TodoService(
            lambda: uow,
            activity_service=activity_service,
            notification_service=notification_service,
        )

    # -- Existing test (create not-a-member) ---------------------------------

    @pytest.mark.asyncio
    async def test_create_requires_member_role(self, uow: FakeUnitOfWork, user_id: UUID) -> None:
        """Creating a workspace todo requires MEMBER+ role."""
        service = TodoService(lambda: uow)
        workspace_id = uuid4()

        # User is not a member of the workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.create(
                user_id=user_id,
                title="WS Todo",
                workspace_id=workspace_id,
            )

    # -- get_all_for_user with workspace_id ----------------------------------

    @pytest.mark.asyncio
    async def test_get_all_should_return_workspace_todos_when_member(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        member: WorkspaceMember,
    ) -> None:
        """get_all_for_user with workspace_id returns workspace todos after membership check."""
        service = TodoService(lambda: uow)
        uow.workspaces.get_member.return_value = member
        expected = [Todo(user_id=user_id, workspace_id=ws_id, title="T1")]
        uow.todos.get_all_for_workspace.return_value = expected

        result = await service.get_all_for_user(user_id, workspace_id=ws_id)

        assert result == expected
        uow.workspaces.get_member.assert_called_once_with(ws_id, user_id)
        uow.todos.get_all_for_workspace.assert_called_once_with(ws_id)

    @pytest.mark.asyncio
    async def test_get_all_should_raise_when_not_a_member(
        self, uow: FakeUnitOfWork, user_id: UUID, ws_id: UUID
    ) -> None:
        """get_all_for_user raises NotAMemberError when user is not in workspace."""
        service = TodoService(lambda: uow)
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_all_for_user(user_id, workspace_id=ws_id)

    # -- get_by_id with workspace_id -----------------------------------------

    @pytest.mark.asyncio
    async def test_get_by_id_should_return_todo_when_workspace_member(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        member: WorkspaceMember,
        ws_todo: Todo,
    ) -> None:
        """get_by_id with workspace_id succeeds when user is a member."""
        service = TodoService(lambda: uow)
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = member

        result = await service.get_by_id(ws_todo.id, user_id, workspace_id=ws_id)

        assert result.id == ws_todo.id

    @pytest.mark.asyncio
    async def test_get_by_id_should_raise_when_todo_workspace_mismatch(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        member: WorkspaceMember,
    ) -> None:
        """get_by_id raises TodoNotFoundError when todo.workspace_id != requested workspace_id."""
        service = TodoService(lambda: uow)
        different_ws = uuid4()
        todo_in_other_ws = Todo(user_id=user_id, workspace_id=different_ws, title="Other WS")
        uow.todos.get.return_value = todo_in_other_ws
        uow.workspaces.get_member.return_value = member

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(todo_in_other_ws.id, user_id, workspace_id=ws_id)

    @pytest.mark.asyncio
    async def test_get_by_id_should_verify_implicit_workspace_membership(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
    ) -> None:
        """get_by_id without explicit workspace_id still checks membership for workspace todos."""
        service = TodoService(lambda: uow)
        ws_todo = Todo(user_id=uuid4(), workspace_id=ws_id, title="WS Todo")
        uow.todos.get.return_value = ws_todo
        # User is NOT a member of the todo's workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(ws_todo.id, user_id)

    # -- create with workspace_id (activity + notification) ------------------

    @pytest.mark.asyncio
    async def test_create_should_log_activity_and_notify_when_workspace(
        self,
        ws_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        member: WorkspaceMember,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> None:
        """Creating a workspace todo logs activity and sends notifications."""
        uow.workspaces.get_member.return_value = member
        uow.todos.get_root_todos.return_value = []
        created_todo = Todo(user_id=user_id, workspace_id=ws_id, title="New WS Task")
        uow.todos.create.return_value = created_todo

        other_member = WorkspaceMember(
            workspace_id=ws_id, user_id=uuid4(), role=WorkspaceRole.MEMBER
        )
        uow.workspaces.get_members.return_value = [member, other_member]

        result = await ws_service.create(
            user_id=user_id,
            title="New WS Task",
            workspace_id=ws_id,
            actor_name="TestUser",
        )

        assert result.title == "New WS Task"
        assert uow.committed

        # Activity was logged
        activity_service.log.assert_called_once()
        log_call = activity_service.log.call_args
        assert log_call is not None
        assert log_call.kwargs["action"] == Actions.TODO_CREATED
        assert log_call.kwargs["workspace_id"] == ws_id

        # Notification was sent
        notification_service.notify.assert_called_once()
        notif_call = notification_service.notify.call_args
        assert notif_call is not None
        assert notif_call.kwargs["type_name"] == NotificationTypes.TASK_CREATED
        assert set(notif_call.kwargs["recipient_ids"]) == {member.user_id, other_member.user_id}

    @pytest.mark.asyncio
    async def test_create_should_reject_parent_in_different_workspace(
        self, uow: FakeUnitOfWork, user_id: UUID, ws_id: UUID, member: WorkspaceMember
    ) -> None:
        """Creating a child todo rejects a parent from a different workspace."""
        service = TodoService(lambda: uow)
        uow.workspaces.get_member.return_value = member

        parent_in_other_ws = Todo(user_id=user_id, workspace_id=uuid4(), title="Other WS Parent")
        uow.todos.get.return_value = parent_in_other_ws

        with pytest.raises(TodoNotFoundError):
            await service.create(
                user_id=user_id,
                title="Child",
                parent_id=parent_in_other_ws.id,
                workspace_id=ws_id,
            )

    # -- update with workspace todo ------------------------------------------

    @pytest.mark.asyncio
    async def test_update_should_check_membership_and_log_activity(
        self,
        ws_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        ws_todo: Todo,
        member: WorkspaceMember,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> None:
        """Updating a workspace todo verifies membership and logs activity diff."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = member
        updated = Todo(
            id=ws_todo.id,
            user_id=user_id,
            workspace_id=ws_id,
            title="Updated Title",
            description="WS description",
            position=0,
        )
        uow.todos.update.return_value = updated
        uow.workspaces.get_members.return_value = [member]

        result = await ws_service.update(
            todo_id=ws_todo.id, user_id=user_id, title="Updated Title", actor_name="Tester"
        )

        assert result.title == "Updated Title"
        assert uow.committed

        # Activity logged with TODO_UPDATED action (title changed)
        activity_service.log.assert_called_once()
        log_call = activity_service.log.call_args
        assert log_call is not None
        log_kw = log_call.kwargs
        assert log_kw["action"] == Actions.TODO_UPDATED
        assert "title" in log_kw["changes"]

        # Notification sent
        notification_service.notify.assert_called_once()
        notif_call = notification_service.notify.call_args
        assert notif_call is not None
        notif_kw = notif_call.kwargs
        assert notif_kw["type_name"] == NotificationTypes.TASK_UPDATED

    @pytest.mark.asyncio
    async def test_update_should_log_completed_action_when_completing_workspace_todo(
        self,
        ws_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        ws_todo: Todo,
        member: WorkspaceMember,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> None:
        """Completing a workspace todo logs activity and notification."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = member
        # After update, the todo will be completed
        completed_todo = Todo(
            id=ws_todo.id,
            user_id=user_id,
            workspace_id=ws_id,
            title=ws_todo.title,
            is_completed=True,
        )
        uow.todos.update.return_value = completed_todo
        uow.workspaces.get_members.return_value = [member]

        await ws_service.update(todo_id=ws_todo.id, user_id=user_id, is_completed=True)

        # Activity action should be TODO_COMPLETED
        log_call = activity_service.log.call_args
        assert log_call is not None
        log_kw = log_call.kwargs
        assert log_kw["action"] == Actions.TODO_COMPLETED

        # Notification type should be TASK_COMPLETED
        notif_call = notification_service.notify.call_args
        assert notif_call is not None
        notif_kw = notif_call.kwargs
        assert notif_kw["type_name"] == NotificationTypes.TASK_COMPLETED

    @pytest.mark.asyncio
    async def test_update_should_raise_when_viewer_tries_to_edit(
        self, uow: FakeUnitOfWork, user_id: UUID, ws_id: UUID, viewer: WorkspaceMember
    ) -> None:
        """Viewer cannot update workspace todos (requires MEMBER+)."""
        service = TodoService(lambda: uow)
        ws_todo = Todo(user_id=user_id, workspace_id=ws_id, title="WS Task")
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = viewer

        with pytest.raises(InsufficientPermissionsError):
            await service.update(todo_id=ws_todo.id, user_id=user_id, title="Nope")

    # -- delete with workspace todo ------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_should_log_activity_and_notify_when_workspace(
        self,
        ws_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        ws_id: UUID,
        ws_todo: Todo,
        member: WorkspaceMember,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> None:
        """Deleting a workspace todo logs activity and notifies before deletion."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = member
        uow.todos.delete.return_value = True
        other_member = WorkspaceMember(
            workspace_id=ws_id, user_id=uuid4(), role=WorkspaceRole.MEMBER
        )
        uow.workspaces.get_members.return_value = [member, other_member]

        result = await ws_service.delete(ws_todo.id, user_id, actor_name="Deleter")

        assert result is True
        assert uow.committed

        # Activity logged with TODO_DELETED
        activity_service.log.assert_called_once()
        log_call = activity_service.log.call_args
        assert log_call is not None
        log_kw = log_call.kwargs
        assert log_kw["action"] == Actions.TODO_DELETED
        assert log_kw["metadata"]["title"] == ws_todo.title

        # Notification sent with TASK_DELETED
        notification_service.notify.assert_called_once()
        notif_call = notification_service.notify.call_args
        assert notif_call is not None
        notif_kw = notif_call.kwargs
        assert notif_kw["type_name"] == NotificationTypes.TASK_DELETED

    @pytest.mark.asyncio
    async def test_delete_should_raise_when_not_a_member(
        self, uow: FakeUnitOfWork, user_id: UUID, ws_id: UUID
    ) -> None:
        """Deleting a workspace todo raises NotAMemberError if not a member."""
        service = TodoService(lambda: uow)
        ws_todo = Todo(user_id=uuid4(), workspace_id=ws_id, title="WS Task")
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.delete(ws_todo.id, user_id)

    @pytest.mark.asyncio
    async def test_delete_should_raise_when_wrong_user_on_personal_todo(
        self, uow: FakeUnitOfWork, user_id: UUID
    ) -> None:
        """Deleting a personal todo owned by another user raises TodoNotFoundError."""
        service = TodoService(lambda: uow)
        other_user_todo = Todo(user_id=uuid4(), title="Someone elses")
        uow.todos.get.return_value = other_user_todo

        with pytest.raises(TodoNotFoundError):
            await service.delete(other_user_todo.id, user_id)


class TestTodoServiceMoveWorkspace:
    """Tests for move_to_workspace functionality."""

    # -- Helpers / fixtures --------------------------------------------------

    @pytest.fixture
    def source_ws_id(self) -> UUID:
        return uuid4()

    @pytest.fixture
    def target_ws_id(self) -> UUID:
        return uuid4()

    @pytest.fixture
    def source_member(self, source_ws_id: UUID, user_id: UUID) -> WorkspaceMember:
        return WorkspaceMember(
            workspace_id=source_ws_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

    @pytest.fixture
    def target_member(self, target_ws_id: UUID, user_id: UUID) -> WorkspaceMember:
        return WorkspaceMember(
            workspace_id=target_ws_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

    @pytest.fixture
    def ws_todo(self, user_id: UUID, source_ws_id: UUID) -> Todo:
        return Todo(
            id=uuid4(),
            user_id=user_id,
            workspace_id=source_ws_id,
            title="WS Task",
            position=0,
        )

    @pytest.fixture
    def child_todo(self, user_id: UUID, source_ws_id: UUID, ws_todo: Todo) -> Todo:
        return Todo(
            id=uuid4(),
            user_id=user_id,
            workspace_id=source_ws_id,
            title="Child Task",
            parent_id=ws_todo.id,
            position=0,
        )

    @pytest.fixture
    def activity_service(self) -> AsyncMock:
        return AsyncMock(spec=ActivityService)

    @pytest.fixture
    def notification_service(self) -> AsyncMock:
        return AsyncMock(spec=NotificationService)

    @pytest.fixture
    def move_service(
        self,
        uow: FakeUnitOfWork,
        activity_service: AsyncMock,
        notification_service: AsyncMock,
    ) -> TodoService:
        return TodoService(
            lambda: uow,
            activity_service=activity_service,
            notification_service=notification_service,
        )

    # -- Happy path tests ---------------------------------------------------

    @pytest.mark.asyncio
    async def test_move_workspace_to_workspace(
        self,
        move_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
        ws_todo: Todo,
    ) -> None:
        """Moving a todo between workspaces updates workspace_id and commits."""
        uow.todos.get.return_value = ws_todo

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = ws_todo
        uow.workspaces.get_members.return_value = [source_member]

        result = await move_service.move_to_workspace(
            todo_id=ws_todo.id,
            user_id=user_id,
            target_workspace_id=target_ws_id,
        )

        assert result.workspace_id == target_ws_id
        assert uow.committed
        uow.tags.detach_all_from_todo.assert_called_once_with(ws_todo.id)

    @pytest.mark.asyncio
    async def test_move_detaches_parent(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
    ) -> None:
        """Moving a child todo detaches it from its parent."""
        parent = Todo(id=uuid4(), user_id=user_id, workspace_id=source_ws_id, title="Parent")
        child = Todo(
            id=uuid4(),
            user_id=user_id,
            workspace_id=source_ws_id,
            title="Child",
            parent_id=parent.id,
        )
        uow.todos.get.return_value = child

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = child

        service = TodoService(lambda: uow)
        await service.move_to_workspace(child.id, user_id, target_ws_id)

        # The child's parent_id should be set to None before update
        assert child.parent_id is None

    @pytest.mark.asyncio
    async def test_move_strips_tags_from_subtree(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
        ws_todo: Todo,
        child_todo: Todo,
    ) -> None:
        """Moving a todo strips tags from itself and all descendants."""

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = [child_todo]
        uow.todos.update.return_value = ws_todo

        service = TodoService(lambda: uow)
        await service.move_to_workspace(ws_todo.id, user_id, target_ws_id)

        # detach_all_from_todo called for parent and child
        assert uow.tags.detach_all_from_todo.call_count == 2
        called_ids = {call.args[0] for call in uow.tags.detach_all_from_todo.call_args_list}
        assert called_ids == {ws_todo.id, child_todo.id}

    @pytest.mark.asyncio
    async def test_move_updates_all_descendants_workspace_id(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
        ws_todo: Todo,
        child_todo: Todo,
    ) -> None:
        """All descendants get the target workspace_id."""

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = [child_todo]
        uow.todos.update.return_value = ws_todo

        service = TodoService(lambda: uow)
        await service.move_to_workspace(ws_todo.id, user_id, target_ws_id)

        assert child_todo.workspace_id == target_ws_id
        # update called for both root todo and child
        assert uow.todos.update.call_count == 2

    # -- Authorization tests ------------------------------------------------

    @pytest.mark.asyncio
    async def test_move_requires_member_in_source_workspace(
        self, uow: FakeUnitOfWork, user_id: UUID, source_ws_id: UUID, ws_todo: Todo
    ) -> None:
        """Moving from a workspace requires MEMBER+ in source."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = None  # not a member

        service = TodoService(lambda: uow)
        with pytest.raises(NotAMemberError):
            await service.move_to_workspace(ws_todo.id, user_id, uuid4())

    @pytest.mark.asyncio
    async def test_move_requires_member_in_target_workspace(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        ws_todo: Todo,
    ) -> None:
        """Moving to a workspace requires MEMBER+ in target."""

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            return None  # not a member in target

        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)

        service = TodoService(lambda: uow)
        with pytest.raises(NotAMemberError):
            await service.move_to_workspace(ws_todo.id, user_id, target_ws_id)

    @pytest.mark.asyncio
    async def test_move_personal_to_workspace(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        target_ws_id: UUID,
        target_member: WorkspaceMember,
    ) -> None:
        """Moving a personal todo into a workspace works for the owner."""
        personal_todo = Todo(id=uuid4(), user_id=user_id, title="Personal Task")
        uow.todos.get.return_value = personal_todo
        uow.workspaces.get_member.return_value = target_member
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = personal_todo

        service = TodoService(lambda: uow)
        result = await service.move_to_workspace(personal_todo.id, user_id, target_ws_id)

        assert result.workspace_id == target_ws_id
        assert uow.committed

    @pytest.mark.asyncio
    async def test_move_workspace_to_personal(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        source_member: WorkspaceMember,
        ws_todo: Todo,
    ) -> None:
        """Moving a workspace todo to personal works for the creator."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = source_member
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = ws_todo

        service = TodoService(lambda: uow)
        result = await service.move_to_workspace(ws_todo.id, user_id, None)

        assert result.workspace_id is None
        assert uow.committed

    @pytest.mark.asyncio
    async def test_move_to_personal_rejects_non_creator(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        source_member: WorkspaceMember,
    ) -> None:
        """Only the todo creator can move it to personal."""
        other_user_id = uuid4()
        ws_todo = Todo(
            id=uuid4(),
            user_id=other_user_id,
            workspace_id=source_ws_id,
            title="Not My Task",
        )
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = source_member

        service = TodoService(lambda: uow)
        with pytest.raises(AppException) as exc_info:
            await service.move_to_workspace(ws_todo.id, user_id, None)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_move_noop_when_same_workspace(
        self,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        source_member: WorkspaceMember,
        ws_todo: Todo,
    ) -> None:
        """Moving to the same workspace is a no-op."""
        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member.return_value = source_member

        service = TodoService(lambda: uow)
        result = await service.move_to_workspace(ws_todo.id, user_id, source_ws_id)

        assert result.id == ws_todo.id
        uow.todos.update.assert_not_called()
        assert not uow.committed

    # -- Activity and notification tests ------------------------------------

    @pytest.mark.asyncio
    async def test_move_logs_activity_in_both_workspaces(
        self,
        move_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
        ws_todo: Todo,
        activity_service: AsyncMock,
    ) -> None:
        """Activity logged in both source (moved_out) and target (moved_in) workspaces."""

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = ws_todo
        uow.workspaces.get_members.return_value = [source_member]

        await move_service.move_to_workspace(ws_todo.id, user_id, target_ws_id)

        assert activity_service.log.call_count == 2
        calls = activity_service.log.call_args_list

        ws_ids = {call.kwargs["workspace_id"] for call in calls}
        assert ws_ids == {source_ws_id, target_ws_id}

        for call in calls:
            assert call.kwargs["action"] == Actions.TODO_WORKSPACE_CHANGED

    @pytest.mark.asyncio
    async def test_move_sends_notifications_to_both_workspaces(
        self,
        move_service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        source_ws_id: UUID,
        target_ws_id: UUID,
        source_member: WorkspaceMember,
        target_member: WorkspaceMember,
        ws_todo: Todo,
        notification_service: AsyncMock,
    ) -> None:
        """Notifications sent to members of both source and target workspaces."""

        def get_member_side_effect(ws_id: Any, uid: Any) -> WorkspaceMember | None:
            if ws_id == source_ws_id:
                return source_member
            if ws_id == target_ws_id:
                return target_member
            return None

        uow.todos.get.return_value = ws_todo
        uow.workspaces.get_member = AsyncMock(side_effect=get_member_side_effect)
        uow.todos.get_all_descendants.return_value = []
        uow.todos.update.return_value = ws_todo
        uow.workspaces.get_members.return_value = [source_member]

        await move_service.move_to_workspace(ws_todo.id, user_id, target_ws_id)

        assert notification_service.notify.call_count == 2
        calls = notification_service.notify.call_args_list

        for call in calls:
            assert call.kwargs["type_name"] == NotificationTypes.TASK_MOVED_WORKSPACE
