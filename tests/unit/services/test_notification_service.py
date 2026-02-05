"""Unit tests for Notification service layer."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from core.exceptions import NotificationRecipientNotFoundError
from domain.entities.notification import (
    Notification,
    NotificationPreference,
    NotificationRecipient,
    NotificationType,
)
from domain.services.notification_service import (
    NOTIFICATION_EXPIRY_DAYS,
    NotificationService,
)

# --- Fake UoW ---


class FakeNotificationRepo:
    """Fake notification repository for testing."""

    def __init__(self):
        self.get_type_by_name = AsyncMock()
        self.get_all_types = AsyncMock(return_value=[])
        self.create = AsyncMock()
        self.get = AsyncMock()
        self.get_recent_for_entity = AsyncMock(return_value=None)
        self.create_recipient = AsyncMock()
        self.create_recipients_batch = AsyncMock(return_value=[])
        self.get_user_notifications = AsyncMock(return_value=[])
        self.get_unread_count = AsyncMock(return_value=0)
        self.mark_read = AsyncMock(return_value=True)
        self.mark_unread = AsyncMock(return_value=True)
        self.mark_all_read = AsyncMock(return_value=0)
        self.soft_delete = AsyncMock(return_value=True)
        self.get_preferences = AsyncMock(return_value=[])
        self.upsert_preference = AsyncMock()
        self.should_notify = AsyncMock(return_value=True)
        self.delete_expired = AsyncMock(return_value=0)


class FakeUnitOfWork:
    """Fake Unit of Work for testing."""

    def __init__(self):
        self.notifications = FakeNotificationRepo()
        self.workspaces = AsyncMock()
        self.committed = False
        self.rolled_back = False

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# --- Fixtures ---


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def service(uow: FakeUnitOfWork) -> NotificationService:
    return NotificationService(lambda: uow)


@pytest.fixture
def actor_id() -> UUID:
    return uuid4()


@pytest.fixture
def workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_type() -> NotificationType:
    return NotificationType(
        name="task.completed",
        template='{actor_name} completed "{entity_title}"',
        is_mandatory=False,
    )


@pytest.fixture
def mandatory_type() -> NotificationType:
    return NotificationType(
        name="member.added",
        template='{actor_name} added you to workspace "{workspace_name}"',
        is_mandatory=True,
    )


# --- Tests: notify() ---


class TestNotifyCreation:
    """Test notification creation via notify()."""

    @pytest.mark.asyncio
    async def test_creates_notification_and_recipients(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() creates notification + batch recipient records."""
        recipient_1 = uuid4()
        recipient_2 = uuid4()
        entity_id = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type

        created_notif = Notification(
            type_name="task.completed",
            type_id=sample_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
        )
        uow.notifications.create.return_value = created_notif

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            recipient_ids=[recipient_1, recipient_2],
            metadata={"actor_name": "Test User", "entity_title": "My Task"},
        )

        assert result is not None
        assert result.type_name == "task.completed"
        uow.notifications.create.assert_called_once()
        uow.notifications.create_recipients_batch.assert_called_once()
        batch_arg = uow.notifications.create_recipients_batch.call_args[0][0]
        assert len(batch_arg) == 2

    @pytest.mark.asyncio
    async def test_excludes_actor_from_recipients(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() removes the actor from the recipient list."""
        other_user = uuid4()
        entity_id = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type
        uow.notifications.create.return_value = Notification(
            type_name="task.completed",
            type_id=sample_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
        )

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            recipient_ids=[actor_id, other_user],
        )

        assert result is not None
        batch_arg = uow.notifications.create_recipients_batch.call_args[0][0]
        assert len(batch_arg) == 1
        assert batch_arg[0].recipient_id == other_user

    @pytest.mark.asyncio
    async def test_returns_none_when_type_not_found(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
    ):
        """notify() returns None when notification type doesn't exist."""
        uow.notifications.get_type_by_name.return_value = None

        result = await service.notify(
            uow=uow,
            type_name="nonexistent.type",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=uuid4(),
            recipient_ids=[uuid4()],
        )

        assert result is None
        uow.notifications.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_no_recipients_remain(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() returns None when only recipient is the actor."""
        uow.notifications.get_type_by_name.return_value = sample_type

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=uuid4(),
            recipient_ids=[actor_id],
        )

        assert result is None
        uow.notifications.create.assert_not_called()


class TestNotifyPreferences:
    """Test preference-aware filtering in notify()."""

    @pytest.mark.asyncio
    async def test_respects_preference_opt_out(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() filters out users who opted out via preferences."""
        opted_in_user = uuid4()
        opted_out_user = uuid4()
        entity_id = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type

        # should_notify returns False for opted_out_user
        async def mock_should_notify(user_id, ws_id, type_name, channel):
            return user_id != opted_out_user

        uow.notifications.should_notify.side_effect = mock_should_notify

        uow.notifications.create.return_value = Notification(
            type_name="task.completed",
            type_id=sample_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
        )

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            recipient_ids=[opted_in_user, opted_out_user],
        )

        assert result is not None
        batch_arg = uow.notifications.create_recipients_batch.call_args[0][0]
        assert len(batch_arg) == 1
        assert batch_arg[0].recipient_id == opted_in_user

    @pytest.mark.asyncio
    async def test_mandatory_bypasses_preferences(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        mandatory_type: NotificationType,
    ):
        """notify() skips preference check for mandatory notification types."""
        recipient = uuid4()
        entity_id = uuid4()

        uow.notifications.get_type_by_name.return_value = mandatory_type
        uow.notifications.create.return_value = Notification(
            type_name="member.added",
            type_id=mandatory_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="workspace",
            entity_id=entity_id,
        )

        result = await service.notify(
            uow=uow,
            type_name="member.added",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="workspace",
            entity_id=entity_id,
            recipient_ids=[recipient],
        )

        assert result is not None
        # should_notify should NOT have been called for mandatory type
        uow.notifications.should_notify.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_none_when_all_opted_out(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() returns None if all non-actor recipients opted out."""
        opted_out_user = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type
        uow.notifications.should_notify.return_value = False

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=uuid4(),
            recipient_ids=[opted_out_user],
        )

        assert result is None
        uow.notifications.create.assert_not_called()


class TestNotifyDeduplication:
    """Test deduplication in notify()."""

    @pytest.mark.asyncio
    async def test_skips_duplicate_within_window(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() returns None when recent duplicate exists within 5-min window."""
        entity_id = uuid4()
        recipient = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type
        # Simulate a recent notification existing
        uow.notifications.get_recent_for_entity.return_value = Notification(
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            created_at=datetime.utcnow() - timedelta(seconds=60),
        )

        result = await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            recipient_ids=[recipient],
        )

        assert result is None
        uow.notifications.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_mandatory_bypasses_deduplication(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        mandatory_type: NotificationType,
    ):
        """notify() does NOT check deduplication for mandatory notifications."""
        entity_id = uuid4()
        recipient = uuid4()

        uow.notifications.get_type_by_name.return_value = mandatory_type
        uow.notifications.create.return_value = Notification(
            type_name="member.added",
            type_id=mandatory_type.id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="workspace",
            entity_id=entity_id,
        )

        result = await service.notify(
            uow=uow,
            type_name="member.added",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="workspace",
            entity_id=entity_id,
            recipient_ids=[recipient],
        )

        assert result is not None
        uow.notifications.get_recent_for_entity.assert_not_called()


class TestNotifyExpiry:
    """Test notification expiry setting."""

    @pytest.mark.asyncio
    async def test_sets_expiry_to_90_days(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
        actor_id: UUID,
        workspace_id: UUID,
        sample_type: NotificationType,
    ):
        """notify() sets expires_at to 90 days from creation."""
        recipient = uuid4()
        entity_id = uuid4()

        uow.notifications.get_type_by_name.return_value = sample_type

        # Capture the notification passed to create()
        created_notif = None

        async def capture_create(notif):
            nonlocal created_notif
            created_notif = notif
            return notif

        uow.notifications.create.side_effect = capture_create

        await service.notify(
            uow=uow,
            type_name="task.completed",
            workspace_id=workspace_id,
            actor_id=actor_id,
            entity_type="todo",
            entity_id=entity_id,
            recipient_ids=[recipient],
        )

        assert created_notif is not None
        assert created_notif.expires_at is not None
        expected_expiry = created_notif.created_at + timedelta(days=NOTIFICATION_EXPIRY_DAYS)
        # Allow 1 second tolerance for timing
        assert abs((created_notif.expires_at - expected_expiry).total_seconds()) < 1


# --- Tests: Read methods ---


class TestGetNotifications:
    """Test get_notifications() feed retrieval."""

    @pytest.mark.asyncio
    async def test_returns_formatted_notifications(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """get_notifications() returns formatted list with unread count."""
        user_id = uuid4()
        workspace_id = uuid4()
        notif_id = uuid4()
        type_id = uuid4()
        recipient_id = uuid4()

        notif = Notification(
            id=notif_id,
            type_name="",
            type_id=type_id,
            workspace_id=workspace_id,
            actor_id=uuid4(),
            entity_type="todo",
            entity_id=uuid4(),
        )
        recipient = NotificationRecipient(
            id=recipient_id,
            notification_id=notif_id,
            recipient_id=user_id,
            is_read=False,
        )

        uow.notifications.get_user_notifications.return_value = [(notif, recipient)]
        uow.notifications.get_all_types.return_value = [
            NotificationType(id=type_id, name="task.completed", template="test"),
        ]
        uow.notifications.get_unread_count.return_value = 1

        notifications, unread_count = await service.get_notifications(
            user_id=user_id, workspace_id=workspace_id
        )

        assert len(notifications) == 1
        assert notifications[0].type == "task.completed"
        assert notifications[0].is_read is False
        assert unread_count == 1

    @pytest.mark.asyncio
    async def test_passes_pagination_params(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """get_notifications() passes cursor and limit to repository."""
        user_id = uuid4()
        cursor = uuid4()

        uow.notifications.get_user_notifications.return_value = []
        uow.notifications.get_all_types.return_value = []
        uow.notifications.get_unread_count.return_value = 0

        await service.get_notifications(user_id=user_id, limit=10, cursor=cursor)

        uow.notifications.get_user_notifications.assert_called_once_with(
            user_id=user_id,
            workspace_id=None,
            is_read=None,
            limit=10,
            cursor=cursor,
        )


class TestGetUnreadCount:
    @pytest.mark.asyncio
    async def test_returns_count(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """get_unread_count() delegates to repository."""
        user_id = uuid4()
        uow.notifications.get_unread_count.return_value = 5

        count = await service.get_unread_count(user_id)

        assert count == 5


# --- Tests: Mark read/unread ---


class TestMarkRead:
    @pytest.mark.asyncio
    async def test_marks_as_read(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """mark_read() calls repository and commits."""
        user_id = uuid4()
        recipient_id = uuid4()

        uow.notifications.mark_read.return_value = True

        await service.mark_read(recipient_id, user_id)

        uow.notifications.mark_read.assert_called_once_with(recipient_id, user_id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """mark_read() raises NotificationRecipientNotFoundError on failure."""
        uow.notifications.mark_read.return_value = False

        with pytest.raises(NotificationRecipientNotFoundError):
            await service.mark_read(uuid4(), uuid4())


class TestMarkUnread:
    @pytest.mark.asyncio
    async def test_marks_as_unread(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """mark_unread() calls repository and commits."""
        user_id = uuid4()
        recipient_id = uuid4()

        uow.notifications.mark_unread.return_value = True

        await service.mark_unread(recipient_id, user_id)

        uow.notifications.mark_unread.assert_called_once_with(recipient_id, user_id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """mark_unread() raises NotificationRecipientNotFoundError on failure."""
        uow.notifications.mark_unread.return_value = False

        with pytest.raises(NotificationRecipientNotFoundError):
            await service.mark_unread(uuid4(), uuid4())


class TestMarkAllRead:
    @pytest.mark.asyncio
    async def test_marks_all_and_returns_count(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """mark_all_read() returns count and commits."""
        user_id = uuid4()
        workspace_id = uuid4()
        uow.notifications.mark_all_read.return_value = 5

        count = await service.mark_all_read(user_id, workspace_id)

        assert count == 5
        uow.notifications.mark_all_read.assert_called_once_with(user_id, workspace_id)
        assert uow.committed


# --- Tests: Delete ---


class TestDeleteNotification:
    @pytest.mark.asyncio
    async def test_soft_deletes(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """delete_notification() calls soft_delete and commits."""
        user_id = uuid4()
        recipient_id = uuid4()

        uow.notifications.soft_delete.return_value = True

        await service.delete_notification(recipient_id, user_id)

        uow.notifications.soft_delete.assert_called_once_with(recipient_id, user_id)
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_when_not_found(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """delete_notification() raises NotificationRecipientNotFoundError on failure."""
        uow.notifications.soft_delete.return_value = False

        with pytest.raises(NotificationRecipientNotFoundError):
            await service.delete_notification(uuid4(), uuid4())


# --- Tests: Preferences ---


class TestGetPreferences:
    @pytest.mark.asyncio
    async def test_returns_user_preferences(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """get_preferences() returns list from repository."""
        user_id = uuid4()
        prefs = [
            NotificationPreference(user_id=user_id, channel="in_app", enabled=True),
            NotificationPreference(user_id=user_id, channel="email", enabled=False),
        ]
        uow.notifications.get_preferences.return_value = prefs

        result = await service.get_preferences(user_id)

        assert len(result) == 2
        assert result[0].channel == "in_app"
        assert result[1].enabled is False


class TestUpdatePreference:
    @pytest.mark.asyncio
    async def test_upserts_preference(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """update_preference() upserts and commits."""
        user_id = uuid4()
        workspace_id = uuid4()

        expected = NotificationPreference(
            user_id=user_id,
            workspace_id=workspace_id,
            notification_type="task.completed",
            channel="in_app",
            enabled=False,
        )
        uow.notifications.upsert_preference.return_value = expected

        result = await service.update_preference(
            user_id=user_id,
            channel="in_app",
            enabled=False,
            workspace_id=workspace_id,
            notification_type="task.completed",
        )

        assert result.enabled is False
        assert result.workspace_id == workspace_id
        assert uow.committed


class TestGetNotificationTypes:
    @pytest.mark.asyncio
    async def test_returns_all_types(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """get_notification_types() returns all types from repository."""
        types = [
            NotificationType(name="task.completed", template="test1"),
            NotificationType(name="member.added", template="test2", is_mandatory=True),
        ]
        uow.notifications.get_all_types.return_value = types

        result = await service.get_notification_types()

        assert len(result) == 2
        assert result[1].is_mandatory is True


# --- Tests: Cleanup ---


class TestCleanupExpired:
    @pytest.mark.asyncio
    async def test_deletes_expired_and_commits(
        self,
        service: NotificationService,
        uow: FakeUnitOfWork,
    ):
        """cleanup_expired() calls delete_expired and commits."""
        uow.notifications.delete_expired.return_value = 42

        count = await service.cleanup_expired()

        assert count == 42
        uow.notifications.delete_expired.assert_called_once()
        assert uow.committed
