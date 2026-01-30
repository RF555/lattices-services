"""Tag repository protocol."""

from typing import Dict, List, Optional, Protocol
from uuid import UUID

from domain.entities.tag import Tag


class ITagRepository(Protocol):
    """Repository interface for Tag entities."""

    async def get(self, id: UUID) -> Optional[Tag]:
        """Get a tag by ID."""
        ...

    async def get_all_for_user(self, user_id: UUID) -> List[Tag]:
        """Get all tags for a user."""
        ...

    async def get_for_todo(self, todo_id: UUID) -> List[Tag]:
        """Get all tags attached to a todo."""
        ...

    async def get_for_todos_batch(self, todo_ids: List[UUID]) -> Dict[UUID, List[Tag]]:
        """Get tags for multiple todos in a single query (batch fetch)."""
        ...

    async def get_by_name(self, user_id: UUID, name: str) -> Optional[Tag]:
        """Get a tag by name for a user."""
        ...

    async def create(self, tag: Tag) -> Tag:
        """Create a new tag."""
        ...

    async def update(self, tag: Tag) -> Tag:
        """Update an existing tag."""
        ...

    async def delete(self, id: UUID) -> bool:
        """Delete a tag and return success status."""
        ...

    async def attach_to_todo(self, tag_id: UUID, todo_id: UUID) -> None:
        """Attach a tag to a todo."""
        ...

    async def detach_from_todo(self, tag_id: UUID, todo_id: UUID) -> None:
        """Detach a tag from a todo."""
        ...

    async def get_usage_count(self, tag_id: UUID) -> int:
        """Get the number of todos using this tag."""
        ...
