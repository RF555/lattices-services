"""Integration tests for Activity API."""

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser
from infrastructure.database.models import ProfileModel


@pytest.fixture
async def activity_client(
    session_factory: async_sessionmaker,
    test_user: TokenUser,
    auth_provider: JWTAuthProvider,
):
    """Create a test client with activity services wired up."""
    from api.dependencies.auth import get_auth_provider, get_current_user
    from api.v1.dependencies import (
        get_activity_service,
        get_group_service,
        get_invitation_service,
        get_tag_service,
        get_todo_service,
        get_workspace_service,
    )
    from domain.services.activity_service import ActivityService
    from domain.services.group_service import GroupService
    from domain.services.invitation_service import InvitationService
    from domain.services.tag_service import TagService
    from domain.services.todo_service import TodoService
    from domain.services.workspace_service import WorkspaceService
    from infrastructure.database.sqlalchemy_uow import SQLAlchemyUnitOfWork
    from main import create_app

    app = create_app()

    async with session_factory() as session:
        from sqlalchemy import select

        stmt = select(ProfileModel).where(ProfileModel.id == test_user.id)
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            profile = ProfileModel(
                id=test_user.id,
                email=test_user.email,
                display_name=test_user.display_name,
            )
            session.add(profile)
            await session.commit()

    async def override_get_user():
        return test_user

    def override_get_auth_provider():
        return auth_provider

    def test_uow_factory():
        return SQLAlchemyUnitOfWork(session_factory)

    activity_service = ActivityService(test_uow_factory)

    app.dependency_overrides[get_current_user] = override_get_user
    app.dependency_overrides[get_auth_provider] = override_get_auth_provider
    app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
        test_uow_factory, activity_service=activity_service
    )
    app.dependency_overrides[get_invitation_service] = lambda: InvitationService(test_uow_factory)
    app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
    app.dependency_overrides[get_activity_service] = lambda: activity_service
    app.dependency_overrides[get_todo_service] = lambda: TodoService(
        test_uow_factory, activity_service=activity_service
    )
    app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


class TestWorkspaceActivity:
    """Tests for workspace activity feed."""

    @pytest.mark.asyncio
    async def test_get_workspace_activity_feed(self, activity_client: AsyncClient):
        """GET /api/v1/workspaces/{ws}/activity returns activity feed."""
        # Create workspace (generates activity)
        create = await activity_client.post(
            "/api/v1/workspaces", json={"name": f"Activity WS {uuid4().hex[:8]}"}
        )
        ws_id = create.json()["data"]["id"]

        response = await activity_client.get(f"/api/v1/workspaces/{ws_id}/activity")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "meta" in data

    @pytest.mark.asyncio
    async def test_get_workspace_activity_not_found(self, activity_client: AsyncClient):
        """Activity feed for non-existent workspace returns 404."""
        response = await activity_client.get(f"/api/v1/workspaces/{uuid4()}/activity")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_workspace_activity_pagination(self, activity_client: AsyncClient):
        """Activity feed respects limit and offset params."""
        create = await activity_client.post(
            "/api/v1/workspaces", json={"name": f"Paginated Activity WS {uuid4().hex[:8]}"}
        )
        ws_id = create.json()["data"]["id"]

        response = await activity_client.get(
            f"/api/v1/workspaces/{ws_id}/activity",
            params={"limit": 5, "offset": 0},
        )

        assert response.status_code == 200
        meta = response.json()["meta"]
        assert meta["limit"] == 5
        assert meta["offset"] == 0


class TestEntityHistory:
    """Tests for entity activity history."""

    @pytest.mark.asyncio
    async def test_get_entity_history(self, activity_client: AsyncClient):
        """GET /api/v1/workspaces/{ws}/activity/{type}/{id} returns history."""
        create = await activity_client.post(
            "/api/v1/workspaces", json={"name": f"Entity History WS {uuid4().hex[:8]}"}
        )
        ws_id = create.json()["data"]["id"]

        response = await activity_client.get(f"/api/v1/workspaces/{ws_id}/activity/todo/{uuid4()}")

        assert response.status_code == 200
        assert "data" in response.json()

    @pytest.mark.asyncio
    async def test_get_entity_history_workspace_not_found(self, activity_client: AsyncClient):
        """Entity history for non-existent workspace returns 404."""
        response = await activity_client.get(
            f"/api/v1/workspaces/{uuid4()}/activity/todo/{uuid4()}"
        )

        assert response.status_code == 404
