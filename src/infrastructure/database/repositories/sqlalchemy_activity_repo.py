"""SQLAlchemy implementation of Activity Log repository."""

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.activity import ActivityLog
from infrastructure.database.models import ActivityLogModel


class SQLAlchemyActivityRepository:
    """SQLAlchemy implementation of IActivityRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, activity: ActivityLog) -> ActivityLog:
        """Create a new activity log entry."""
        model = self._to_model(activity)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_for_workspace(
        self,
        workspace_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ActivityLog]:
        """Get activity log entries for a workspace, ordered by newest first."""
        stmt = (
            select(ActivityLogModel)
            .where(ActivityLogModel.workspace_id == workspace_id)
            .order_by(ActivityLogModel.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_for_entity(
        self,
        entity_type: str,
        entity_id: UUID,
        limit: int = 50,
    ) -> List[ActivityLog]:
        """Get activity log entries for a specific entity."""
        stmt = (
            select(ActivityLogModel)
            .where(
                ActivityLogModel.entity_type == entity_type,
                ActivityLogModel.entity_id == entity_id,
            )
            .order_by(ActivityLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_for_user(
        self,
        user_id: UUID,
        limit: int = 50,
    ) -> List[ActivityLog]:
        """Get activity log entries by a specific user."""
        stmt = (
            select(ActivityLogModel)
            .where(ActivityLogModel.actor_id == user_id)
            .order_by(ActivityLogModel.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    def _to_entity(self, model: ActivityLogModel) -> ActivityLog:
        """Convert ORM model to domain entity."""
        return ActivityLog(
            id=model.id,
            workspace_id=model.workspace_id,
            actor_id=model.actor_id,
            action=model.action,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            changes=model.changes,
            metadata=model.metadata_,
            created_at=model.created_at,
        )

    def _to_model(self, entity: ActivityLog) -> ActivityLogModel:
        """Convert domain entity to ORM model."""
        return ActivityLogModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            actor_id=entity.actor_id,
            action=entity.action,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            changes=entity.changes,
            metadata_=entity.metadata,
            created_at=entity.created_at,
        )
