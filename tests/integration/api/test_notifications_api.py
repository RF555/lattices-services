"""Integration tests for Notifications API."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from infrastructure.database.models import (
    NotificationModel,
    NotificationRecipientModel,
    NotificationTypeModel,
    ProfileModel,
    WorkspaceMemberModel,
    WorkspaceModel,
)


@pytest.fixture
async def notification_client(session_factory, test_user, auth_provider) -> AsyncClient:
    """
    Create authenticated test client with notification service wired up.

    Sets up:
    - In-memory SQLite database with all tables
    - Test user profile
    - A workspace with the test user as owner
    - Seeded notification types
    - Notification service dependency override
    """
    from api.dependencies.auth import get_auth_provider, get_current_user
    from api.v1.dependencies import (
        get_notification_service,
        get_tag_service,
        get_todo_service,
        get_workspace_service,
    )
    from domain.services.notification_service import NotificationService
    from domain.services.tag_service import TagService
    from domain.services.todo_service import TodoService
    from domain.services.workspace_service import WorkspaceService
    from infrastructure.database.sqlalchemy_uow import SQLAlchemyUnitOfWork
    from main import create_app

    app = create_app()

    # Seed profile
    async with session_factory() as session:
        stmt = select(ProfileModel).where(ProfileModel.id == test_user.id)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            session.add(
                ProfileModel(
                    id=test_user.id,
                    email=test_user.email,
                    display_name=test_user.display_name,
                )
            )
            await session.commit()

    # Seed notification types
    async with session_factory() as session:
        stmt = select(NotificationTypeModel).where(NotificationTypeModel.name == "task.completed")
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            types = [
                NotificationTypeModel(
                    name="task.completed",
                    template='{actor_name} completed "{entity_title}"',
                    is_mandatory=False,
                ),
                NotificationTypeModel(
                    name="task.updated",
                    template='{actor_name} updated "{entity_title}"',
                    is_mandatory=False,
                ),
                NotificationTypeModel(
                    name="member.added",
                    template='{actor_name} added you to workspace "{workspace_name}"',
                    is_mandatory=True,
                ),
            ]
            session.add_all(types)
            await session.commit()

    # Create test workspace and add user as owner
    workspace_id = uuid4()
    async with session_factory() as session:
        stmt = select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            session.add(
                WorkspaceModel(
                    id=workspace_id,
                    name="Test Workspace",
                    slug=f"test-workspace-{workspace_id.hex[:8]}",
                    created_by=test_user.id,
                )
            )
            session.add(
                WorkspaceMemberModel(
                    workspace_id=workspace_id,
                    user_id=test_user.id,
                    role="owner",
                )
            )
            await session.commit()

    # Create notification + recipient records for the test user
    async with session_factory() as session:
        # Get the task.completed type ID
        stmt = select(NotificationTypeModel).where(NotificationTypeModel.name == "task.completed")
        result = await session.execute(stmt)
        task_completed_type = result.scalar_one()

        notif1_id = uuid4()
        notif2_id = uuid4()
        session.add_all(
            [
                NotificationModel(
                    id=notif1_id,
                    type_id=task_completed_type.id,
                    workspace_id=workspace_id,
                    actor_id=test_user.id,
                    entity_type="todo",
                    entity_id=uuid4(),
                    metadata_={"actor_name": "Test User", "entity_title": "Task 1"},
                ),
                NotificationModel(
                    id=notif2_id,
                    type_id=task_completed_type.id,
                    workspace_id=workspace_id,
                    actor_id=test_user.id,
                    entity_type="todo",
                    entity_id=uuid4(),
                    metadata_={"actor_name": "Test User", "entity_title": "Task 2"},
                ),
            ]
        )
        await session.flush()

        recipient1_id = uuid4()
        recipient2_id = uuid4()
        session.add_all(
            [
                NotificationRecipientModel(
                    id=recipient1_id,
                    notification_id=notif1_id,
                    recipient_id=test_user.id,
                    is_read=False,
                ),
                NotificationRecipientModel(
                    id=recipient2_id,
                    notification_id=notif2_id,
                    recipient_id=test_user.id,
                    is_read=False,
                ),
            ]
        )
        await session.commit()

    # Override dependencies
    async def override_get_user():
        return test_user

    def override_get_auth_provider():
        return auth_provider

    def test_uow_factory():
        return SQLAlchemyUnitOfWork(session_factory)

    def override_get_notification_service():
        return NotificationService(test_uow_factory)

    def override_get_todo_service():
        return TodoService(test_uow_factory)

    def override_get_tag_service():
        return TagService(test_uow_factory)

    def override_get_workspace_service():
        return WorkspaceService(test_uow_factory)

    app.dependency_overrides[get_current_user] = override_get_user
    app.dependency_overrides[get_auth_provider] = override_get_auth_provider
    app.dependency_overrides[get_notification_service] = override_get_notification_service
    app.dependency_overrides[get_todo_service] = override_get_todo_service
    app.dependency_overrides[get_tag_service] = override_get_tag_service
    app.dependency_overrides[get_workspace_service] = override_get_workspace_service

    # Store IDs on client for test access
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.workspace_id = str(workspace_id)  # type: ignore[attr-defined]
        c.recipient1_id = str(recipient1_id)  # type: ignore[attr-defined]
        c.recipient2_id = str(recipient2_id)  # type: ignore[attr-defined]
        yield c

    app.dependency_overrides.clear()


class TestWorkspaceNotifications:
    """Integration tests for workspace-scoped notification endpoints."""

    @pytest.mark.asyncio
    async def test_list_workspace_notifications(self, notification_client: AsyncClient):
        """Test GET /workspaces/{wid}/notifications returns notification feed."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        response = await notification_client.get(f"/api/v1/workspaces/{wid}/notifications")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert len(data["data"]) >= 2
        assert "unread_count" in data["meta"]

    @pytest.mark.asyncio
    async def test_list_workspace_notifications_with_filter(self, notification_client: AsyncClient):
        """Test GET with is_read filter."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        response = await notification_client.get(
            f"/api/v1/workspaces/{wid}/notifications?is_read=false"
        )

        assert response.status_code == 200
        data = response.json()
        # All seeded notifications are unread
        for notif in data["data"]:
            assert notif["is_read"] is False

    @pytest.mark.asyncio
    async def test_get_workspace_unread_count(self, notification_client: AsyncClient):
        """Test GET /workspaces/{wid}/notifications/unread-count."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        response = await notification_client.get(
            f"/api/v1/workspaces/{wid}/notifications/unread-count"
        )

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 2

    @pytest.mark.asyncio
    async def test_mark_notification_read(self, notification_client: AsyncClient):
        """Test PATCH .../notifications/{rid}/read marks as read."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        rid = notification_client.recipient1_id  # type: ignore[attr-defined]

        response = await notification_client.patch(
            f"/api/v1/workspaces/{wid}/notifications/{rid}/read"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_mark_notification_unread(self, notification_client: AsyncClient):
        """Test PATCH .../notifications/{rid}/unread marks as unread."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        rid = notification_client.recipient1_id  # type: ignore[attr-defined]

        # First mark as read
        await notification_client.patch(f"/api/v1/workspaces/{wid}/notifications/{rid}/read")

        # Then mark as unread
        response = await notification_client.patch(
            f"/api/v1/workspaces/{wid}/notifications/{rid}/unread"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_mark_all_read(self, notification_client: AsyncClient):
        """Test POST .../notifications/mark-all-read."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]

        response = await notification_client.post(
            f"/api/v1/workspaces/{wid}/notifications/mark-all-read"
        )

        assert response.status_code == 200
        data = response.json()
        assert "count" in data

    @pytest.mark.asyncio
    async def test_delete_notification(self, notification_client: AsyncClient):
        """Test DELETE .../notifications/{rid} soft-deletes."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        rid = notification_client.recipient2_id  # type: ignore[attr-defined]

        response = await notification_client.delete(f"/api/v1/workspaces/{wid}/notifications/{rid}")

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_mark_read_not_found(self, notification_client: AsyncClient):
        """Test 404 when marking non-existent notification as read."""
        wid = notification_client.workspace_id  # type: ignore[attr-defined]
        fake_rid = uuid4()

        response = await notification_client.patch(
            f"/api/v1/workspaces/{wid}/notifications/{fake_rid}/read"
        )

        assert response.status_code == 404


class TestUserNotifications:
    """Integration tests for user-scoped notification endpoints."""

    @pytest.mark.asyncio
    async def test_list_user_notifications(self, notification_client: AsyncClient):
        """Test GET /users/me/notifications returns cross-workspace feed."""
        response = await notification_client.get("/api/v1/users/me/notifications")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data
        assert len(data["data"]) >= 2

    @pytest.mark.asyncio
    async def test_get_user_unread_count(self, notification_client: AsyncClient):
        """Test GET /users/me/notifications/unread-count."""
        response = await notification_client.get("/api/v1/users/me/notifications/unread-count")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data
        assert data["count"] >= 2

    @pytest.mark.asyncio
    async def test_mark_all_user_notifications_read(self, notification_client: AsyncClient):
        """Test POST /users/me/notifications/mark-all-read."""
        response = await notification_client.post("/api/v1/users/me/notifications/mark-all-read")

        assert response.status_code == 200
        data = response.json()
        assert "count" in data


class TestNotificationPreferences:
    """Integration tests for notification preference endpoints."""

    @pytest.mark.asyncio
    async def test_get_preferences_empty(self, notification_client: AsyncClient):
        """Test GET /users/me/notification-preferences returns empty list initially."""
        response = await notification_client.get("/api/v1/users/me/notification-preferences")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    @pytest.mark.asyncio
    async def test_upsert_preference(self, notification_client: AsyncClient):
        """Test PUT /users/me/notification-preferences creates preference."""
        response = await notification_client.put(
            "/api/v1/users/me/notification-preferences",
            json={
                "channel": "in_app",
                "enabled": False,
                "notification_type": "task.completed",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["channel"] == "in_app"
        assert data["enabled"] is False
        assert data["notification_type"] == "task.completed"

    @pytest.mark.asyncio
    async def test_upsert_preference_update(self, notification_client: AsyncClient):
        """Test PUT /users/me/notification-preferences updates existing preference."""
        # Create
        await notification_client.put(
            "/api/v1/users/me/notification-preferences",
            json={"channel": "in_app", "enabled": False},
        )

        # Update
        response = await notification_client.put(
            "/api/v1/users/me/notification-preferences",
            json={"channel": "in_app", "enabled": True},
        )

        assert response.status_code == 200
        assert response.json()["enabled"] is True

    @pytest.mark.asyncio
    async def test_upsert_preference_invalid_channel(self, notification_client: AsyncClient):
        """Test validation error for invalid channel."""
        response = await notification_client.put(
            "/api/v1/users/me/notification-preferences",
            json={"channel": "sms", "enabled": True},
        )

        assert response.status_code == 422


class TestNotificationTypes:
    """Integration tests for notification types endpoint."""

    @pytest.mark.asyncio
    async def test_list_notification_types(self, notification_client: AsyncClient):
        """Test GET /users/me/notification-types returns seeded types."""
        response = await notification_client.get("/api/v1/users/me/notification-types")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) >= 3
        names = [t["name"] for t in data["data"]]
        assert "task.completed" in names
        assert "member.added" in names
