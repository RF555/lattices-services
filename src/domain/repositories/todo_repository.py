"""Todo repository protocol."""

from typing import Protocol
from uuid import UUID

from domain.entities.todo import Todo


class ITodoRepository(Protocol):
    """Repository interface for Todo entities."""

    async def get(self, id: UUID) -> Todo | None:
        """Get a todo by ID."""
        ...

    async def get_all_for_user(self, user_id: UUID) -> list[Todo]:
        """Get all todos for a user (flat list)."""
        ...

    async def get_all_for_workspace(self, workspace_id: UUID) -> list[Todo]:
        """Get all todos for a workspace (flat list)."""
        ...

    async def get_root_todos(self, user_id: UUID) -> list[Todo]:
        """Get all root-level todos (no parent) for a user."""
        ...

    async def get_children(self, parent_id: UUID) -> list[Todo]:
        """Get all direct children of a todo."""
        ...

    async def create(self, todo: Todo) -> Todo:
        """Create a new todo."""
        ...

    async def update(self, todo: Todo) -> Todo:
        """Update an existing todo."""
        ...

    async def delete(self, id: UUID) -> bool:
        """Delete a todo and return success status."""
        ...

    async def get_child_counts_batch(
        self, todo_ids: list[UUID]
    ) -> dict[UUID, tuple[int, int]]:
        """Get child counts for multiple todos in a single query.

        Returns a mapping of parent_id -> (child_count, completed_child_count).
        """
        ...
