"""SQLAlchemy implementation of Todo repository."""

from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.todo import Todo
from infrastructure.database.models import TodoModel


class SQLAlchemyTodoRepository:
    """SQLAlchemy implementation of ITodoRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> Todo | None:
        """Get a todo by ID."""
        stmt = select(TodoModel).where(TodoModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_all_for_user(self, user_id: UUID) -> list[Todo]:
        """Get all todos for a user (flat list for tree assembly)."""
        stmt = (
            select(TodoModel)
            .where(TodoModel.user_id == user_id)
            .order_by(TodoModel.position, TodoModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_all_for_workspace(self, workspace_id: UUID) -> list[Todo]:
        """Get all todos for a workspace (flat list for tree assembly)."""
        stmt = (
            select(TodoModel)
            .where(TodoModel.workspace_id == workspace_id)
            .order_by(TodoModel.position, TodoModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_root_todos(self, user_id: UUID) -> list[Todo]:
        """Get all root-level todos (no parent) for a user."""
        stmt = (
            select(TodoModel)
            .where(TodoModel.user_id == user_id, TodoModel.parent_id.is_(None))
            .order_by(TodoModel.position)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_children(self, parent_id: UUID) -> list[Todo]:
        """Get all direct children of a todo."""
        stmt = (
            select(TodoModel)
            .where(TodoModel.parent_id == parent_id)
            .order_by(TodoModel.position)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def create(self, todo: Todo) -> Todo:
        """Create a new todo."""
        model = self._to_model(todo)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(self, todo: Todo) -> Todo:
        """Update an existing todo."""
        stmt = select(TodoModel).where(TodoModel.id == todo.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Todo {todo.id} not found")

        # Update fields
        model.parent_id = todo.parent_id
        model.title = todo.title
        model.description = todo.description
        model.is_completed = todo.is_completed
        model.position = todo.position
        model.updated_at = todo.updated_at
        model.completed_at = todo.completed_at

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, id: UUID) -> bool:
        """Delete a todo and all its descendants (cascade)."""
        stmt = select(TodoModel).where(TodoModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_child_counts_batch(
        self, todo_ids: list[UUID]
    ) -> dict[UUID, tuple[int, int]]:
        """Get child counts for multiple todos in a single query."""
        if not todo_ids:
            return {}

        stmt = (
            select(
                TodoModel.parent_id,
                func.count().label("child_count"),
                func.sum(
                    case((TodoModel.is_completed == True, 1), else_=0)  # noqa: E712
                ).label("completed_child_count"),
            )
            .where(TodoModel.parent_id.in_(todo_ids))
            .group_by(TodoModel.parent_id)
        )
        result = await self._session.execute(stmt)
        return {
            row.parent_id: (row.child_count, row.completed_child_count or 0)
            for row in result
        }

    def _to_entity(self, model: TodoModel) -> Todo:
        """Convert ORM model to domain entity."""
        return Todo(
            id=model.id,
            user_id=model.user_id,
            parent_id=model.parent_id,
            workspace_id=model.workspace_id,
            title=model.title,
            description=model.description,
            is_completed=model.is_completed,
            position=model.position,
            created_at=model.created_at,
            updated_at=model.updated_at,
            completed_at=model.completed_at,
        )

    def _to_model(self, entity: Todo) -> TodoModel:
        """Convert domain entity to ORM model."""
        return TodoModel(
            id=entity.id,
            user_id=entity.user_id,
            parent_id=entity.parent_id,
            workspace_id=entity.workspace_id,
            title=entity.title,
            description=entity.description,
            is_completed=entity.is_completed,
            position=entity.position,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            completed_at=entity.completed_at,
        )
