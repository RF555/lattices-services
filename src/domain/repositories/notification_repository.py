"""Notification repository protocol."""

from typing import Protocol
from uuid import UUID

from domain.entities.notification import (
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationType,
)


class INotificationRepository(Protocol):
    """Repository interface for Notification entities."""

    # --- Types ---

    async def get_type_by_name(self, name: str) -> NotificationType | None:
        """Get a notification type by its name."""
        ...

    async def get_all_types(self) -> list[NotificationType]:
        """Get all notification types."""
        ...

    # --- Notifications ---

    async def create(self, notification: Notification) -> Notification:
        """Create a new notification."""
        ...

    async def get(self, notification_id: UUID) -> Notification | None:
        """Get a notification by ID."""
        ...

    async def get_recent_for_entity(
        self,
        type_name: str,
        entity_type: str,
        entity_id: UUID,
        actor_id: UUID,
        window_seconds: int = 300,
    ) -> Notification | None:
        """Check for a recent notification of the same type for deduplication."""
        ...

    # --- Recipients ---

    async def create_recipient(self, recipient: NotificationRecipient) -> NotificationRecipient:
        """Create a single notification recipient record."""
        ...

    async def create_recipients_batch(
        self, recipients: list[NotificationRecipient]
    ) -> list[NotificationRecipient]:
        """Batch-create notification recipient records."""
        ...

    async def get_user_notifications(
        self,
        user_id: UUID,
        workspace_id: UUID | None = None,
        is_read: bool | None = None,
        limit: int = 20,
        cursor: UUID | None = None,
    ) -> list[tuple[Notification, NotificationRecipient]]:
        """Get paginated notification feed for a user."""
        ...

    async def get_unread_count(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Get the count of unread notifications for a user."""
        ...

    async def mark_read(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Mark a notification as read for a user."""
        ...

    async def mark_unread(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Mark a notification as unread for a user."""
        ...

    async def mark_all_read(self, user_id: UUID, workspace_id: UUID | None = None) -> int:
        """Mark all notifications as read for a user. Returns count updated."""
        ...

    async def soft_delete(self, recipient_id: UUID, user_id: UUID) -> bool:
        """Soft-delete a notification for a user."""
        ...

    # --- Preferences ---

    async def get_preferences(self, user_id: UUID) -> list[NotificationPreference]:
        """Get all notification preferences for a user."""
        ...

    async def upsert_preference(self, pref: NotificationPreference) -> NotificationPreference:
        """Upsert a notification preference."""
        ...

    async def should_notify(
        self,
        user_id: UUID,
        workspace_id: UUID,
        type_name: str,
        channel: str,
    ) -> bool:
        """Check if a user should receive a notification based on preferences."""
        ...

    # --- Cleanup ---

    async def delete_expired(self, batch_size: int = 10000) -> int:
        """Delete expired notifications. Returns count deleted."""
        ...
