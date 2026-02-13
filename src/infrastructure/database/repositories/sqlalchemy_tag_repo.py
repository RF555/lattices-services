"""SQLAlchemy implementation of Tag repository."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.tag import Tag
from infrastructure.database.models import TagModel, TodoTagModel


class SQLAlchemyTagRepository:
    """SQLAlchemy implementation of ITagRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> Tag | None:
        """Get a tag by ID."""
        stmt = select(TagModel).where(TagModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_all_for_user(self, user_id: UUID) -> list[Tag]:
        """Get all tags for a user."""
        stmt = select(TagModel).where(TagModel.user_id == user_id).order_by(TagModel.name)
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_all_for_workspace(self, workspace_id: UUID) -> list[Tag]:
        """Get all tags for a workspace."""
        stmt = select(TagModel).where(TagModel.workspace_id == workspace_id).order_by(TagModel.name)
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_by_name_in_workspace(self, workspace_id: UUID, name: str) -> Tag | None:
        """Get a tag by name within a workspace."""
        stmt = select(TagModel).where(
            TagModel.workspace_id == workspace_id,
            TagModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_for_todo(self, todo_id: UUID) -> list[Tag]:
        """Get all tags attached to a todo."""
        stmt = (
            select(TagModel)
            .join(TodoTagModel, TagModel.id == TodoTagModel.tag_id)
            .where(TodoTagModel.todo_id == todo_id)
            .order_by(TagModel.name)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_for_todos_batch(self, todo_ids: list[UUID]) -> dict[UUID, list[Tag]]:
        """Get tags for multiple todos in a single query."""
        if not todo_ids:
            return {}

        stmt = (
            select(TodoTagModel.todo_id, TagModel)
            .join(TagModel, TodoTagModel.tag_id == TagModel.id)
            .where(TodoTagModel.todo_id.in_(todo_ids))
            .order_by(TagModel.name)
        )
        result = await self._session.execute(stmt)

        tags_by_todo: dict[UUID, list[Tag]] = defaultdict(list)
        for todo_id, tag_model in result:
            tags_by_todo[todo_id].append(self._to_entity(tag_model))

        return dict(tags_by_todo)

    async def get_by_name(self, user_id: UUID, name: str) -> Tag | None:
        """Get a tag by name for a user."""
        stmt = select(TagModel).where(
            TagModel.user_id == user_id,
            TagModel.name == name,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def create(self, tag: Tag) -> Tag:
        """Create a new tag."""
        model = self._to_model(tag)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(self, tag: Tag) -> Tag:
        """Update an existing tag."""
        stmt = select(TagModel).where(TagModel.id == tag.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Tag {tag.id} not found")

        model.name = tag.name
        model.color_hex = tag.color_hex

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, id: UUID) -> bool:
        """Delete a tag."""
        stmt = select(TagModel).where(TagModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def attach_to_todo(self, tag_id: UUID, todo_id: UUID) -> None:
        """Attach a tag to a todo."""
        # Check if already attached
        stmt = select(TodoTagModel).where(
            TodoTagModel.tag_id == tag_id,
            TodoTagModel.todo_id == todo_id,
        )
        result = await self._session.execute(stmt)
        if result.scalar_one_or_none():
            return  # Already attached

        model = TodoTagModel(tag_id=tag_id, todo_id=todo_id)
        self._session.add(model)
        await self._session.flush()

    async def detach_from_todo(self, tag_id: UUID, todo_id: UUID) -> None:
        """Detach a tag from a todo."""
        stmt = delete(TodoTagModel).where(
            TodoTagModel.tag_id == tag_id,
            TodoTagModel.todo_id == todo_id,
        )
        await self._session.execute(stmt)
        await self._session.flush()

    async def detach_all_from_todo(self, todo_id: UUID) -> None:
        """Remove all tag associations from a todo."""
        stmt = delete(TodoTagModel).where(TodoTagModel.todo_id == todo_id)
        await self._session.execute(stmt)
        await self._session.flush()

    async def get_usage_count(self, tag_id: UUID) -> int:
        """Get the number of todos using this tag."""
        stmt = select(func.count()).select_from(TodoTagModel).where(TodoTagModel.tag_id == tag_id)
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def get_usage_counts_batch(self, tag_ids: list[UUID]) -> dict[UUID, int]:
        """Get usage counts for multiple tags in a single query."""
        if not tag_ids:
            return {}
        stmt = (
            select(
                TodoTagModel.tag_id,
                func.count().label("usage_count"),
            )
            .where(TodoTagModel.tag_id.in_(tag_ids))
            .group_by(TodoTagModel.tag_id)
        )
        result = await self._session.execute(stmt)
        return {row.tag_id: row.usage_count for row in result}

    def _to_entity(self, model: TagModel) -> Tag:
        """Convert ORM model to domain entity."""
        return Tag(
            id=model.id,
            user_id=model.user_id,
            workspace_id=model.workspace_id,
            name=model.name,
            color_hex=model.color_hex,
            created_at=model.created_at,
        )

    def _to_model(self, entity: Tag) -> TagModel:
        """Convert domain entity to ORM model."""
        return TagModel(
            id=entity.id,
            user_id=entity.user_id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            color_hex=entity.color_hex,
            created_at=entity.created_at,
        )
