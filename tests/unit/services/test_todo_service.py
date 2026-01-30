"""Unit tests for Todo service layer."""

from datetime import datetime
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from domain.entities.todo import Todo
from domain.services.todo_service import TodoService
from core.exceptions import TodoNotFoundError, AppException


class FakeUnitOfWork:
    """Fake Unit of Work for testing."""

    def __init__(self):
        self.todos = AsyncMock()
        self.tags = AsyncMock()
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


@pytest.fixture
def uow() -> FakeUnitOfWork:
    """Create a fresh fake UoW."""
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> TodoService:
    """Create service with fake UoW."""
    return TodoService(lambda: uow)


@pytest.fixture
def user_id() -> UUID:
    return uuid4()


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
    ):
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
    ):
        """Test get_by_id returns todo when found."""
        uow.todos.get.return_value = sample_todo

        result = await service.get_by_id(sample_todo.id, user_id)

        assert result.id == sample_todo.id

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """Test get_by_id raises TodoNotFoundError when not found."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_raises_when_wrong_user(
        self, service: TodoService, uow: FakeUnitOfWork, sample_todo: Todo
    ):
        """Test get_by_id raises when todo belongs to different user."""
        uow.todos.get.return_value = sample_todo

        with pytest.raises(TodoNotFoundError):
            await service.get_by_id(sample_todo.id, uuid4())  # Different user


class TestTodoServiceCreate:
    @pytest.mark.asyncio
    async def test_creates_root_todo(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """Test creating a root-level todo."""
        expected = Todo(user_id=user_id, title="New Task")
        uow.todos.get_root_todos.return_value = []
        uow.todos.create.return_value = expected

        result = await service.create(user_id=user_id, title="New Task")

        uow.todos.create.assert_called_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_creates_child_todo(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ):
        """Test creating a child todo."""
        parent = sample_todo
        uow.todos.get.return_value = parent
        uow.todos.get_children.return_value = []
        uow.todos.create.return_value = Todo(
            user_id=user_id, title="Child", parent_id=parent.id
        )

        result = await service.create(
            user_id=user_id, title="Child", parent_id=parent.id
        )

        assert uow.committed

    @pytest.mark.asyncio
    async def test_create_with_invalid_parent_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """Test creating todo with non-existent parent raises error."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.create(
                user_id=user_id, title="Task", parent_id=uuid4()
            )


class TestTodoServiceUpdate:
    @pytest.mark.asyncio
    async def test_updates_title(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ):
        """Test updating todo title."""
        uow.todos.get.return_value = sample_todo
        uow.todos.update.return_value = sample_todo

        result = await service.update(
            todo_id=sample_todo.id, user_id=user_id, title="Updated"
        )

        uow.todos.update.assert_called_once()
        assert uow.committed

    @pytest.mark.asyncio
    async def test_completes_todo(
        self,
        service: TodoService,
        uow: FakeUnitOfWork,
        user_id: UUID,
        sample_todo: Todo,
    ):
        """Test completing a todo."""
        uow.todos.get.return_value = sample_todo
        uow.todos.update.return_value = sample_todo

        await service.update(
            todo_id=sample_todo.id, user_id=user_id, is_completed=True
        )

        assert sample_todo.is_completed
        assert sample_todo.completed_at is not None

    @pytest.mark.asyncio
    async def test_update_not_found_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """Test updating non-existent todo raises."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.update(
                todo_id=uuid4(), user_id=user_id, title="Updated"
            )


class TestTodoServiceChildCounts:
    @pytest.mark.asyncio
    async def test_returns_empty_dict_for_empty_input(
        self, service: TodoService, uow: FakeUnitOfWork
    ):
        """Empty list returns {} without touching repo."""
        result = await service.get_child_counts_batch([])

        assert result == {}
        uow.todos.get_child_counts_batch.assert_not_called()

    @pytest.mark.asyncio
    async def test_delegates_to_repo(
        self, service: TodoService, uow: FakeUnitOfWork
    ):
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
    ):
        """Test deleting a todo."""
        uow.todos.get.return_value = sample_todo
        uow.todos.delete.return_value = True

        result = await service.delete(sample_todo.id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_delete_not_found_raises(
        self, service: TodoService, uow: FakeUnitOfWork, user_id: UUID
    ):
        """Test deleting non-existent todo raises."""
        uow.todos.get.return_value = None

        with pytest.raises(TodoNotFoundError):
            await service.delete(uuid4(), user_id)
