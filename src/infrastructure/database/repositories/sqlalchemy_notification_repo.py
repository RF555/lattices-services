"""SQLAlchemy implementation of Notification repository."""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.notification import (
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationType,
)
from infrastructure.database.models import (
    NotificationModel,
    NotificationPreferenceModel,
    NotificationRecipientModel,
    NotificationTypeModel,
)


class SQLAlchemyNotificationRepository:
    """SQLAlchemy implementation of INotificationRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Types ---

    async def get_type_by_name(self, name: str) -> NotificationType | None:
        """Get a notification type by its name."""
        stmt = select(NotificationTypeModel).where(NotificationTypeModel.name == name)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._type_to_entity(model) if model else None

    async def get_all_types(self) -> list[NotificationType]:
        """Get all notification types."""
        stmt = select(NotificationTypeModel).order_by(NotificationTypeModel.name)
        result = await self._session.execute(stmt)
        return [self._type_to_entity(m) for m in result.scalars()]

    # --- Notifications ---

    async def create(self, notification: Notification) -> Notification:
        """Create a new notification."""
        model = self._to_model(notification)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def get(self, notification_id: UUID) -> Notification | None:
        """Get a notification by ID."""
        stmt = select(NotificationModel).where(NotificationModel.id == notification_id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_recent_for_entity(
        self,
        type_name: str,
        entity_type: str,
        entity_id: UUID,
        actor_id: UUID,
        window_seconds: int = 300,
    ) -> Notification | None:
        """Check for a recent notification for deduplication."""
        cutoff = datetime.utcnow() - timedelta(seconds=window_seconds)
        stmt = (
            select(NotificationModel)
            .join(
                NotificationTypeModel,
                NotificationModel.type_id == NotificationTypeModel.id,
            )
            .where(
                NotificationTypeModel.name == type_name,
                NotificationModel.entity_type == entity_type,
                NotificationModel.entity_id == entity_id,
                NotificationModel.actor_id == actor_id,
                NotificationModel.created_at > cutoff,
            )
            .order_by(NotificationModel.created_at.desc())
            .limit(1)
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    # --- Recipients ---

    async def create_recipient(self, recipient: NotificationRecipient) -> NotificationRecipient:
        """Create a single notification recipient record."""
        model = self._recipient_to_model(recipient)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._recipient_to_entity(model)

    async def create_recipients_batch(
        self, recipients: list[NotificationRecipient]
    ) -> list[NotificationRecipient]:
        """Batch-create notification recipient records."""
        models = [self._recipient_to_model(r) for r in recipients]
        self._session.add_all(models)
        await self._session.flush()
        for model in models:
            await self._session.refresh(model)
        return [self._recipient_to_entity(m) for m in models]

    async def get_user_notifications(
        self,
        user_id: UUID,
        workspace_id: UUID | None = None,
        is_read: bool | None = None,
        limit: int = 20,
        cursor: UUID | None = None,
    ) -> list[tuple[Notification, NotificationRecipient]]:
        """Get paginated notification feed for a user."""
        stmt = (
            select(NotificationModel, NotificationRecipientModel)
            .join(
                NotificationRecipientModel,
                NotificationModel.id == NotificationRecipientModel.notification_id,
            )
            .where(
                NotificationRecipientModel.recipient_id == user_id,
                NotificationRecipientModel.is_deleted.is_(False),
            )
        )

        if workspace_id is not None:
            stmt = stmt.where(NotificationModel.workspace_id == workspace_id)

        if is_read is not None:
            stmt = stmt.where(NotificationRecipientModel.is_read == is_read)

        if cursor is not None:
            stmt = stmt.where(NotificationRecipientModel.id < cursor)

        stmt = stmt.order_by(NotificationRecipientModel.id.desc()).limit(limit)

        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            (self._to_entity(n_model), self._recipient_to_entity(nr_model))
            for n_model, nr_model in rows
        ]

    async def get_unread_count(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Get the count of unread notifications for a user."""
        stmt = select(func.count(NotificationRecipientModel.id)).where(
            NotificationRecipientModel.recipient_id == user_id,
            NotificationRecipientModel.is_read.is_(False),
            NotificationRecipientModel.is_deleted.is_(False),
        )

        if workspace_id is not None:
            stmt = stmt.join(
                NotificationModel,
                NotificationRecipientModel.notification_id == NotificationModel.id,
            ).where(NotificationModel.workspace_id == workspace_id)

        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def mark_read(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Mark a notification as read for a user."""
        stmt = (
            update(NotificationRecipientModel)
            .where(
                NotificationRecipientModel.id == recipient_id,
                NotificationRecipientModel.recipient_id == user_id,
            )
            .values(is_read=True, read_at=datetime.utcnow())
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[return-value]

    async def mark_unread(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Mark a notification as unread for a user."""
        stmt = (
            update(NotificationRecipientModel)
            .where(
                NotificationRecipientModel.id == recipient_id,
                NotificationRecipientModel.recipient_id == user_id,
            )
            .values(is_read=False, read_at=None)
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[return-value]

    async def mark_all_read(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        if workspace_id is not None:
            # Filter by workspace via subquery on notifications
            notification_ids_subq = (
                select(NotificationModel.id)
                .where(NotificationModel.workspace_id == workspace_id)
                .scalar_subquery()
            )
            stmt = (
                update(NotificationRecipientModel)
                .where(
                    NotificationRecipientModel.recipient_id == user_id,
                    NotificationRecipientModel.is_read.is_(False),
                    NotificationRecipientModel.is_deleted.is_(False),
                    NotificationRecipientModel.notification_id.in_(notification_ids_subq),
                )
                .values(is_read=True, read_at=datetime.utcnow())
            )
        else:
            stmt = (
                update(NotificationRecipientModel)
                .where(
                    NotificationRecipientModel.recipient_id == user_id,
                    NotificationRecipientModel.is_read.is_(False),
                    NotificationRecipientModel.is_deleted.is_(False),
                )
                .values(is_read=True, read_at=datetime.utcnow())
            )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    async def soft_delete(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Soft-delete a notification for a user."""
        stmt = (
            update(NotificationRecipientModel)
            .where(
                NotificationRecipientModel.id == recipient_id,
                NotificationRecipientModel.recipient_id == user_id,
            )
            .values(is_deleted=True, deleted_at=datetime.utcnow())
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0  # type: ignore[return-value]

    # --- Preferences ---

    async def get_preferences(self, user_id: UUID) -> list[NotificationPreference]:
        """Get all notification preferences for a user."""
        stmt = select(NotificationPreferenceModel).where(
            NotificationPreferenceModel.user_id == user_id
        )
        result = await self._session.execute(stmt)
        return [self._pref_to_entity(m) for m in result.scalars()]

    async def upsert_preference(self, pref: NotificationPreference) -> NotificationPreference:
        """Upsert a notification preference."""
        # Try to find existing preference with matching unique constraint
        stmt = select(NotificationPreferenceModel).where(
            NotificationPreferenceModel.user_id == pref.user_id,
            NotificationPreferenceModel.workspace_id == pref.workspace_id
            if pref.workspace_id
            else NotificationPreferenceModel.workspace_id.is_(None),
            NotificationPreferenceModel.notification_type == pref.notification_type
            if pref.notification_type
            else NotificationPreferenceModel.notification_type.is_(None),
            NotificationPreferenceModel.channel == pref.channel,
        )
        result = await self._session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.enabled = pref.enabled
            await self._session.flush()
            await self._session.refresh(existing)
            return self._pref_to_entity(existing)

        model = self._pref_to_model(pref)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._pref_to_entity(model)

    async def should_notify(
        self,
        user_id: UUID,
        workspace_id: UUID,
        type_name: str,
        channel: str,
    ) -> bool:
        """Check if a user should receive a notification based on preferences.

        Resolution order (most specific wins):
        1. user + workspace + type + channel
        2. user + workspace + channel (type=NULL)
        3. user + channel (workspace=NULL, type=NULL)
        4. System default: enabled (True)
        """
        # Level 1: user + workspace + type + channel
        stmt = select(NotificationPreferenceModel.enabled).where(
            NotificationPreferenceModel.user_id == user_id,
            NotificationPreferenceModel.workspace_id == workspace_id,
            NotificationPreferenceModel.notification_type == type_name,
            NotificationPreferenceModel.channel == channel,
        )
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        if val is not None:
            return val

        # Level 2: user + workspace + channel (any type)
        stmt = select(NotificationPreferenceModel.enabled).where(
            NotificationPreferenceModel.user_id == user_id,
            NotificationPreferenceModel.workspace_id == workspace_id,
            NotificationPreferenceModel.notification_type.is_(None),
            NotificationPreferenceModel.channel == channel,
        )
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        if val is not None:
            return val

        # Level 3: user + channel (global)
        stmt = select(NotificationPreferenceModel.enabled).where(
            NotificationPreferenceModel.user_id == user_id,
            NotificationPreferenceModel.workspace_id.is_(None),
            NotificationPreferenceModel.notification_type.is_(None),
            NotificationPreferenceModel.channel == channel,
        )
        result = await self._session.execute(stmt)
        val = result.scalar_one_or_none()
        if val is not None:
            return val

        # Level 4: System default
        return True

    # --- Cleanup ---

    async def delete_expired(self, batch_size: int = 10000) -> int:
        """Delete expired notifications. Returns count deleted."""
        stmt = (
            delete(NotificationModel)
            .where(
                NotificationModel.expires_at.is_not(None),
                NotificationModel.expires_at < datetime.utcnow(),
            )
            .execution_options(synchronize_session=False)
        )
        result = await self._session.execute(stmt)
        return result.rowcount  # type: ignore[return-value]

    # --- Conversion methods ---

    def _type_to_entity(self, model: NotificationTypeModel) -> NotificationType:
        """Convert NotificationTypeModel to domain entity."""
        return NotificationType(
            id=model.id,
            name=model.name,
            description=model.description,
            template=model.template,
            default_channels=model.default_channels or ["in_app"],
            is_mandatory=model.is_mandatory,
            created_at=model.created_at,
        )

    def _to_entity(self, model: NotificationModel) -> Notification:
        """Convert NotificationModel to domain entity."""
        return Notification(
            id=model.id,
            type_name="",  # Populated by caller if needed
            type_id=model.type_id,
            workspace_id=model.workspace_id,
            actor_id=model.actor_id,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            metadata=model.metadata_,
            created_at=model.created_at,
            expires_at=model.expires_at,
        )

    def _to_model(self, entity: Notification) -> NotificationModel:
        """Convert Notification domain entity to ORM model."""
        return NotificationModel(
            id=entity.id,
            type_id=entity.type_id,
            workspace_id=entity.workspace_id,
            actor_id=entity.actor_id,
            entity_type=entity.entity_type,
            entity_id=entity.entity_id,
            metadata_=entity.metadata,
            created_at=entity.created_at,
            expires_at=entity.expires_at,
        )

    def _recipient_to_entity(self, model: NotificationRecipientModel) -> NotificationRecipient:
        """Convert NotificationRecipientModel to domain entity."""
        return NotificationRecipient(
            id=model.id,
            notification_id=model.notification_id,
            recipient_id=model.recipient_id,
            is_read=model.is_read,
            read_at=model.read_at,
            is_deleted=model.is_deleted,
            deleted_at=model.deleted_at,
        )

    def _recipient_to_model(self, entity: NotificationRecipient) -> NotificationRecipientModel:
        """Convert NotificationRecipient domain entity to ORM model."""
        return NotificationRecipientModel(
            id=entity.id,
            notification_id=entity.notification_id,
            recipient_id=entity.recipient_id,
            is_read=entity.is_read,
            read_at=entity.read_at,
            is_deleted=entity.is_deleted,
            deleted_at=entity.deleted_at,
        )

    def _pref_to_entity(self, model: NotificationPreferenceModel) -> NotificationPreference:
        """Convert NotificationPreferenceModel to domain entity."""
        return NotificationPreference(
            id=model.id,
            user_id=model.user_id,
            workspace_id=model.workspace_id,
            notification_type=model.notification_type,
            channel=model.channel,
            enabled=model.enabled,
        )

    def _pref_to_model(self, entity: NotificationPreference) -> NotificationPreferenceModel:
        """Convert NotificationPreference domain entity to ORM model."""
        return NotificationPreferenceModel(
            id=entity.id,
            user_id=entity.user_id,
            workspace_id=entity.workspace_id,
            notification_type=entity.notification_type,
            channel=entity.channel,
            enabled=entity.enabled,
        )
