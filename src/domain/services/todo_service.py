"""Todo service layer with business logic."""

from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple, cast
from uuid import UUID

from core.exceptions import AppException, ErrorCode, TodoNotFoundError
from domain.entities.todo import Todo
from domain.repositories.unit_of_work import IUnitOfWork


class TodoService:
    """Service layer for Todo business logic."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get_child_counts_batch(
        self, todo_ids: List[UUID]
    ) -> Dict[UUID, Tuple[int, int]]:
        """Get child counts for multiple todos.

        Returns a mapping of parent_id -> (child_count, completed_child_count).
        """
        if not todo_ids:
            return {}
        async with self._uow_factory() as uow:
            return await uow.todos.get_child_counts_batch(todo_ids)  # type: ignore[no-any-return]

    async def get_all_for_user(self, user_id: UUID) -> List[Todo]:
        """Get all todos for a user (flat list for tree assembly)."""
        async with self._uow_factory() as uow:
            return await uow.todos.get_all_for_user(user_id)  # type: ignore[no-any-return]

    async def get_by_id(self, todo_id: UUID, user_id: UUID) -> Todo:
        """Get a specific todo, ensuring user ownership."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)

            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            return todo

    async def create(
        self,
        user_id: UUID,
        title: str,
        description: Optional[str] = None,
        parent_id: Optional[UUID] = None,
    ) -> Todo:
        """Create a new todo."""
        async with self._uow_factory() as uow:
            # Validate parent exists and belongs to user
            if parent_id:
                parent = await uow.todos.get(parent_id)
                if not parent or parent.user_id != user_id:
                    raise TodoNotFoundError(str(parent_id))

            # Get position for new todo (last in list)
            if parent_id:
                siblings = await uow.todos.get_children(parent_id)
            else:
                siblings = await uow.todos.get_root_todos(user_id)
            position = len(siblings)

            todo = Todo(
                user_id=user_id,
                parent_id=parent_id,
                title=title,
                description=description,
                position=position,
            )

            created = await uow.todos.create(todo)
            await uow.commit()

            return created

    async def update(
        self,
        todo_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_completed: Optional[bool] = None,
        parent_id: object = ...,  # Sentinel to detect explicit None
        position: Optional[int] = None,
    ) -> Todo:
        """Update an existing todo."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)

            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            # Validate new parent if changing
            if parent_id is not ... and parent_id != todo.parent_id:
                if parent_id is not None:
                    # Check parent exists and belongs to user
                    parent = await uow.todos.get(cast(UUID, parent_id))
                    if not parent or parent.user_id != user_id:
                        raise TodoNotFoundError(str(parent_id))

                    # Prevent circular reference
                    if await self._would_create_cycle(uow, todo_id, cast(UUID, parent_id)):
                        raise AppException(
                            ErrorCode.CIRCULAR_REFERENCE,
                            "Cannot move task to its own descendant",
                            400,
                        )

                todo.parent_id = cast(Optional[UUID], parent_id)

            # Update fields
            if title is not None:
                todo.title = title
            if description is not None:
                todo.description = description
            if position is not None:
                todo.position = position

            # Handle completion state
            if is_completed is not None:
                if is_completed and not todo.is_completed:
                    todo.complete()
                elif not is_completed and todo.is_completed:
                    todo.uncomplete()

            todo.updated_at = datetime.utcnow()

            updated = await uow.todos.update(todo)
            await uow.commit()

            return updated

    async def delete(self, todo_id: UUID, user_id: UUID) -> bool:
        """Delete a todo and all its descendants (cascade)."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)

            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            deleted = await uow.todos.delete(todo_id)
            await uow.commit()

            return deleted  # type: ignore[no-any-return]

    async def _would_create_cycle(
        self, uow: IUnitOfWork, todo_id: UUID, new_parent_id: UUID
    ) -> bool:
        """Check if moving todo to new_parent would create a cycle."""
        current_id: Optional[UUID] = new_parent_id

        while current_id:
            if current_id == todo_id:
                return True

            current = await uow.todos.get(current_id)
            if not current:
                break

            current_id = current.parent_id

        return False
