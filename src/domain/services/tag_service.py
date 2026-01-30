"""Tag service layer with business logic."""

from typing import Dict, List, Optional
from uuid import UUID

from core.exceptions import AppException, ErrorCode, TagNotFoundError, TodoNotFoundError
from domain.entities.tag import Tag


class TagService:
    """Service layer for Tag business logic."""

    def __init__(self, uow_factory):
        self._uow_factory = uow_factory

    async def get_all_for_user(self, user_id: UUID) -> List[dict]:
        """Get all tags for user with usage counts."""
        async with self._uow_factory() as uow:
            tags = await uow.tags.get_all_for_user(user_id)
            result = []
            for tag in tags:
                count = await uow.tags.get_usage_count(tag.id)
                result.append({
                    "tag": tag,
                    "usage_count": count,
                })
            return result

    async def get_by_id(self, tag_id: UUID, user_id: UUID) -> Tag:
        """Get a specific tag, ensuring user ownership."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag or tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))
            return tag

    async def create(
        self,
        user_id: UUID,
        name: str,
        color_hex: str = "#3B82F6",
    ) -> Tag:
        """Create a new tag."""
        async with self._uow_factory() as uow:
            # Check for duplicate name
            existing = await uow.tags.get_by_name(user_id, name)
            if existing:
                raise AppException(
                    ErrorCode.DUPLICATE_TAG,
                    f"Tag '{name}' already exists",
                    409,
                    {"name": name},
                )

            tag = Tag(
                user_id=user_id,
                name=name,
                color_hex=color_hex,
            )

            created = await uow.tags.create(tag)
            await uow.commit()
            return created

    async def update(
        self,
        tag_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        color_hex: Optional[str] = None,
    ) -> Tag:
        """Update an existing tag."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag or tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            if name and name != tag.name:
                # Check for duplicate name
                existing = await uow.tags.get_by_name(user_id, name)
                if existing:
                    raise AppException(
                        ErrorCode.DUPLICATE_TAG,
                        f"Tag '{name}' already exists",
                        409,
                        {"name": name},
                    )
                tag.name = name

            if color_hex:
                tag.color_hex = color_hex

            updated = await uow.tags.update(tag)
            await uow.commit()
            return updated

    async def delete(self, tag_id: UUID, user_id: UUID) -> bool:
        """Delete a tag (detaches from all todos via cascade)."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag or tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            deleted = await uow.tags.delete(tag_id)
            await uow.commit()
            return deleted

    async def attach_to_todo(
        self,
        tag_id: UUID,
        todo_id: UUID,
        user_id: UUID,
    ) -> None:
        """Attach a tag to a todo."""
        async with self._uow_factory() as uow:
            # Verify tag belongs to user
            tag = await uow.tags.get(tag_id)
            if not tag or tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            # Verify todo belongs to user
            todo = await uow.todos.get(todo_id)
            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            await uow.tags.attach_to_todo(tag_id, todo_id)
            await uow.commit()

    async def detach_from_todo(
        self,
        tag_id: UUID,
        todo_id: UUID,
        user_id: UUID,
    ) -> None:
        """Detach a tag from a todo."""
        async with self._uow_factory() as uow:
            # Verify ownership
            tag = await uow.tags.get(tag_id)
            if not tag or tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            todo = await uow.todos.get(todo_id)
            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            await uow.tags.detach_from_todo(tag_id, todo_id)
            await uow.commit()

    async def get_tags_for_todo(self, todo_id: UUID, user_id: UUID) -> List[Tag]:
        """Get all tags attached to a todo."""
        async with self._uow_factory() as uow:
            # Verify ownership
            todo = await uow.todos.get(todo_id)
            if not todo or todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            return await uow.tags.get_for_todo(todo_id)

    async def get_tags_for_todos_batch(
        self, todo_ids: List[UUID]
    ) -> Dict[UUID, List[Tag]]:
        """Get tags for multiple todos in a single query (batch fetch)."""
        if not todo_ids:
            return {}
        async with self._uow_factory() as uow:
            return await uow.tags.get_for_todos_batch(todo_ids)
