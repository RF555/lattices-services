"""SQLAlchemy implementation of Invitation repository."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.invitation import Invitation, InvitationStatus
from infrastructure.database.models import InvitationModel


class SQLAlchemyInvitationRepository:
    """SQLAlchemy implementation of IInvitationRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, invitation: Invitation) -> Invitation:
        """Create a new invitation."""
        model = self._to_model(invitation)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get_by_token_hash(self, token_hash: str) -> Invitation | None:
        """Get an invitation by its hashed token."""
        stmt = select(InvitationModel).where(InvitationModel.token_hash == token_hash)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_for_workspace(self, workspace_id: UUID) -> list[Invitation]:
        """Get all invitations for a workspace."""
        stmt = (
            select(InvitationModel)
            .where(InvitationModel.workspace_id == workspace_id)
            .order_by(InvitationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_for_email(self, email: str) -> list[Invitation]:
        """Get all invitations for an email address."""
        stmt = (
            select(InvitationModel)
            .where(InvitationModel.email == email)
            .order_by(InvitationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_pending_for_email(self, email: str) -> list[Invitation]:
        """Get all pending (non-expired) invitations for an email address."""
        now = datetime.utcnow()
        stmt = (
            select(InvitationModel)
            .where(
                InvitationModel.email == email,
                InvitationModel.status == InvitationStatus.PENDING.value,
                InvitationModel.expires_at > now,
            )
            .order_by(InvitationModel.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def get_pending_for_workspace_email(
        self, workspace_id: UUID, email: str
    ) -> Invitation | None:
        """Get a pending invitation for a specific workspace and email."""
        now = datetime.utcnow()
        stmt = select(InvitationModel).where(
            InvitationModel.workspace_id == workspace_id,
            InvitationModel.email == email,
            InvitationModel.status == InvitationStatus.PENDING.value,
            InvitationModel.expires_at > now,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def update_status(self, id: UUID, status: InvitationStatus) -> Invitation:
        """Update the status of an invitation."""
        stmt = select(InvitationModel).where(InvitationModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Invitation {id} not found")

        model.status = status.value
        if status == InvitationStatus.ACCEPTED:
            model.accepted_at = datetime.utcnow()

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, id: UUID) -> bool:
        """Delete an invitation."""
        stmt = select(InvitationModel).where(InvitationModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def expire_old_invitations(self) -> int:
        """Mark all expired pending invitations. Returns count of updated rows."""
        now = datetime.utcnow()
        stmt = (
            update(InvitationModel)
            .where(
                InvitationModel.status == InvitationStatus.PENDING.value,
                InvitationModel.expires_at <= now,
            )
            .values(status=InvitationStatus.EXPIRED.value)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount  # type: ignore[attr-defined, no-any-return]

    def _to_entity(self, model: InvitationModel) -> Invitation:
        """Convert ORM model to domain entity."""
        return Invitation(
            id=model.id,
            workspace_id=model.workspace_id,
            email=model.email,
            role=model.role,
            token_hash=model.token_hash,
            invited_by=model.invited_by,
            status=InvitationStatus(model.status),
            created_at=model.created_at,
            expires_at=model.expires_at,
            accepted_at=model.accepted_at,
        )

    def _to_model(self, entity: Invitation) -> InvitationModel:
        """Convert domain entity to ORM model."""
        return InvitationModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            email=entity.email,
            role=entity.role,
            token_hash=entity.token_hash,
            invited_by=entity.invited_by,
            status=entity.status.value,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
            accepted_at=entity.accepted_at,
        )
