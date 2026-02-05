"""Notification service layer for creating and managing notifications."""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import structlog

from core.exceptions import NotificationRecipientNotFoundError
from domain.entities.notification import (
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationType,
    NotificationView,
)
from domain.repositories.unit_of_work import IUnitOfWork

logger = structlog.get_logger()

NOTIFICATION_EXPIRY_DAYS = 90
DEDUP_WINDOW_SECONDS = 300  # 5 minutes


class NotificationService:
    """Service layer for notification creation and management."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    # --- In-transaction notification creation ---

    async def notify(
        self,
        uow: IUnitOfWork,
        type_name: str,
        workspace_id: UUID,
        actor_id: UUID,
        entity_type: str,
        entity_id: UUID,
        recipient_ids: list[UUID],
        metadata: dict[str, Any] | None = None,
    ) -> Notification | None:
        """Create a notification within an existing UoW transaction.

        This method is designed to be called from other services
        within their existing transaction context (same pattern as
        ActivityService.log()).

        Args:
            uow: The active Unit of Work (caller manages commit).
            type_name: The notification type name (use NotificationTypes constants).
            workspace_id: The workspace where the event occurred.
            actor_id: The user who performed the action.
            entity_type: The type of entity affected.
            entity_id: The ID of the entity affected.
            recipient_ids: List of user IDs to notify.
            metadata: Optional denormalized data (actor_name, entity_title, etc.).

        Returns:
            The created Notification, or None if skipped (no recipients, dedup, etc.).
        """
        # 1. Look up notification type
        notif_type = await uow.notifications.get_type_by_name(type_name)
        if not notif_type:
            logger.warning(
                "notification_type_not_found",
                type_name=type_name,
            )
            return None

        # 2. Filter recipients
        filtered_ids = set(recipient_ids)

        # Remove actor (no self-notification)
        filtered_ids.discard(actor_id)

        # Check preferences (unless mandatory)
        if not notif_type.is_mandatory:
            eligible_ids: set[UUID] = set()
            for uid in filtered_ids:
                should = await uow.notifications.should_notify(
                    uid, workspace_id, type_name, "in_app"
                )
                if should:
                    eligible_ids.add(uid)
            filtered_ids = eligible_ids

        # 3. If no recipients remain, skip
        if not filtered_ids:
            return None

        # 4. Check deduplication (skip for mandatory notifications)
        if not notif_type.is_mandatory:
            recent = await uow.notifications.get_recent_for_entity(
                type_name=type_name,
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=actor_id,
                window_seconds=DEDUP_WINDOW_SECONDS,
            )
            if recent:
                logger.debug(
                    "notification_deduplicated",
                    type_name=type_name,
                    entity_id=str(entity_id),
                )
                return None

        # 5. Create notification
        now = datetime.utcnow()
        notification = Notification(
            type_name=type_name,
            type_id=notif_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {},
            created_at=now,
            expires_at=now + timedelta(days=NOTIFICATION_EXPIRY_DAYS),
        )

        created = await uow.notifications.create(notification)

        # 6. Batch-create recipient records (fan-out on write)
        recipients = [
            NotificationRecipient(
                notification_id=created.id,
                recipient_id=uid,
            )
            for uid in filtered_ids
        ]
        await uow.notifications.create_recipients_batch(recipients)

        return created

    # --- Read methods (use own UoW context) ---

    async def get_notifications(
        self,
        user_id: UUID,
        workspace_id: UUID | None = None,
        is_read: bool | None = None,
        limit: int = 20,
        cursor: UUID | None = None,
    ) -> tuple[list[NotificationView], int]:
        """Get paginated notification feed.

        Returns:
            Tuple of (notification_list, unread_count).
            Each NotificationView includes recipient fields (id, is_read, etc.).
        """
        async with self._uow_factory() as uow:
            results = await uow.notifications.get_user_notifications(
                user_id=user_id,
                workspace_id=workspace_id,
                is_read=is_read,
                limit=limit,
                cursor=cursor,
            )

            # Build type name cache (one query for all types)
            all_types = await uow.notifications.get_all_types()
            type_cache: dict[UUID | None, str] = {t.id: t.name for t in all_types}

            notifications: list[NotificationView] = []
            for notif, recipient in results:
                notifications.append(
                    NotificationView(
                        id=recipient.id,
                        notification_id=notif.id,
                        type=type_cache.get(notif.type_id, ""),
                        workspace_id=notif.workspace_id,
                        actor_id=notif.actor_id,
                        entity_type=notif.entity_type,
                        entity_id=notif.entity_id,
                        metadata=notif.metadata or {},
                        is_read=recipient.is_read,
                        read_at=recipient.read_at,
                        created_at=notif.created_at,
                    )
                )

            unread_count = await uow.notifications.get_unread_count(user_id, workspace_id)

            return notifications, unread_count

    async def get_unread_count(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Get the count of unread notifications."""
        async with self._uow_factory() as uow:
            return await uow.notifications.get_unread_count(user_id, workspace_id)

    async def mark_read(self, recipient_id: UUID, user_id: UUID) -> None:
        """Mark a notification as read for a user."""
        async with self._uow_factory() as uow:
            success = await uow.notifications.mark_read(recipient_id, user_id)
            if not success:
                raise NotificationRecipientNotFoundError(str(recipient_id))
            await uow.commit()

    async def mark_unread(self, recipient_id: UUID, user_id: UUID) -> None:
        """Mark a notification as unread for a user."""
        async with self._uow_factory() as uow:
            success = await uow.notifications.mark_unread(recipient_id, user_id)
            if not success:
                raise NotificationRecipientNotFoundError(str(recipient_id))
            await uow.commit()

    async def mark_all_read(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Mark all notifications as read. Returns count of marked."""
        async with self._uow_factory() as uow:
            count = await uow.notifications.mark_all_read(user_id, workspace_id)
            await uow.commit()
            return count

    async def delete_notification(self, recipient_id: UUID, user_id: UUID) -> None:
        """Soft-delete a notification for a user."""
        async with self._uow_factory() as uow:
            success = await uow.notifications.soft_delete(recipient_id, user_id)
            if not success:
                raise NotificationRecipientNotFoundError(str(recipient_id))
            await uow.commit()

    # --- Preference methods ---

    async def get_preferences(self, user_id: UUID) -> list[NotificationPreference]:
        """Get all notification preferences for a user."""
        async with self._uow_factory() as uow:
            return await uow.notifications.get_preferences(user_id)

    async def update_preference(
        self,
        user_id: UUID,
        channel: str,
        enabled: bool,
        workspace_id: UUID | None = None,
        notification_type: str | None = None,
    ) -> NotificationPreference:
        """Upsert a notification preference."""
        async with self._uow_factory() as uow:
            pref = NotificationPreference(
                user_id=user_id,
                workspace_id=workspace_id,
                notification_type=notification_type,
                channel=channel,
                enabled=enabled,
            )
            result = await uow.notifications.upsert_preference(pref)
            await uow.commit()
            return result

    async def get_notification_types(self) -> list[NotificationType]:
        """Get all available notification types (for preferences UI)."""
        async with self._uow_factory() as uow:
            return await uow.notifications.get_all_types()

    # --- Cleanup ---

    async def cleanup_expired(self) -> int:
        """Delete expired notifications. Called by scheduled task."""
        async with self._uow_factory() as uow:
            count = await uow.notifications.delete_expired()
            await uow.commit()
            return count
