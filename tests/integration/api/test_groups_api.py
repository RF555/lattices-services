"""Integration tests for Groups API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser
from infrastructure.database.models import ProfileModel


@pytest.fixture
async def group_client(
    session_factory: async_sessionmaker[AsyncSession],
    test_user: TokenUser,
    auth_provider: JWTAuthProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with workspace and group services wired up."""
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

    # Ensure test user profile exists
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

    async def override_get_user() -> TokenUser:
        return test_user

    def override_get_auth_provider() -> JWTAuthProvider:
        return auth_provider

    def test_uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(session_factory)

    activity_service = ActivityService(test_uow_factory)

    app.dependency_overrides[get_current_user] = override_get_user
    app.dependency_overrides[get_auth_provider] = override_get_auth_provider
    app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
        test_uow_factory, activity_service=activity_service
    )
    app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
    app.dependency_overrides[get_activity_service] = lambda: activity_service
    app.dependency_overrides[get_invitation_service] = lambda: InvitationService(test_uow_factory)
    app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
    app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def workspace_id(group_client: AsyncClient) -> str:
    """Create a workspace and return its ID for group tests."""
    unique_name = f"Group Test WS {uuid4().hex[:8]}"
    response = await group_client.post("/api/v1/workspaces", json={"name": unique_name})
    assert response.status_code == 201, f"Workspace creation failed: {response.json()}"
    return str(response.json()["data"]["id"])


class TestGroupsCRUD:
    """Tests for group CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_group(self, group_client: AsyncClient, workspace_id: str) -> None:
        """POST /api/v1/workspaces/{ws}/groups returns 201."""
        response = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Dev Team", "description": "Development team"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == "Dev Team"
        assert data["workspace_id"] == workspace_id

    @pytest.mark.asyncio
    async def test_list_groups(self, group_client: AsyncClient, workspace_id: str) -> None:
        """GET /api/v1/workspaces/{ws}/groups returns list."""
        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "List Group"},
        )

        response = await group_client.get(f"/api/v1/workspaces/{workspace_id}/groups")

        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    @pytest.mark.asyncio
    async def test_update_group(self, group_client: AsyncClient, workspace_id: str) -> None:
        """PATCH /api/v1/workspaces/{ws}/groups/{id} updates group."""
        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Update Group"},
        )
        group_id = create.json()["data"]["id"]

        response = await group_client.patch(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}",
            json={"name": "Updated Group"},
        )

        assert response.status_code == 200
        assert response.json()["data"]["name"] == "Updated Group"

    @pytest.mark.asyncio
    async def test_delete_group(self, group_client: AsyncClient, workspace_id: str) -> None:
        """DELETE /api/v1/workspaces/{ws}/groups/{id} returns 204."""
        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Delete Group"},
        )
        group_id = create.json()["data"]["id"]

        response = await group_client.delete(f"/api/v1/workspaces/{workspace_id}/groups/{group_id}")

        assert response.status_code == 204


class TestGroupMembers:
    """Tests for group member management."""

    @pytest.mark.asyncio
    async def test_list_group_members(self, group_client: AsyncClient, workspace_id: str) -> None:
        """GET /api/v1/workspaces/{ws}/groups/{id}/members returns members."""
        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Members Group"},
        )
        group_id = create.json()["data"]["id"]

        response = await group_client.get(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members"
        )

        assert response.status_code == 200
        # Creator should be auto-added as group admin
        members = response.json()["data"]
        assert len(members) >= 1

    @pytest.mark.asyncio
    async def test_add_group_member(
        self,
        group_client: AsyncClient,
        workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /api/v1/workspaces/{ws}/groups/{id}/members adds member."""
        # Create second user and add to workspace
        second_user_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=second_user_id,
                email=f"grp-{second_user_id}@example.com",
                display_name="Group Member",
            )
            session.add(profile)
            await session.commit()

        # Add to workspace first
        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(second_user_id), "role": "member"},
        )

        # Create group
        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Add Member Group"},
        )
        group_id = create.json()["data"]["id"]

        # Add to group
        response = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members",
            json={"user_id": str(second_user_id), "role": "member"},
        )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_add_group_member_duplicate(
        self,
        group_client: AsyncClient,
        workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """Adding same member twice returns 409."""
        dup_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=dup_id,
                email=f"grp-dup-{dup_id}@example.com",
                display_name="Dup Member",
            )
            session.add(profile)
            await session.commit()

        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(dup_id), "role": "member"},
        )

        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Dup Member Group"},
        )
        group_id = create.json()["data"]["id"]

        # First add
        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members",
            json={"user_id": str(dup_id), "role": "member"},
        )

        # Duplicate
        response = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members",
            json={"user_id": str(dup_id), "role": "member"},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_remove_group_member(
        self,
        group_client: AsyncClient,
        workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """DELETE /api/v1/workspaces/{ws}/groups/{gid}/members/{uid} removes member."""
        rm_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=rm_id,
                email=f"grp-rm-{rm_id}@example.com",
                display_name="Remove Member",
            )
            session.add(profile)
            await session.commit()

        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/members",
            json={"user_id": str(rm_id), "role": "member"},
        )

        create = await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups",
            json={"name": "Remove Member Group"},
        )
        group_id = create.json()["data"]["id"]

        await group_client.post(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members",
            json={"user_id": str(rm_id), "role": "member"},
        )

        response = await group_client.delete(
            f"/api/v1/workspaces/{workspace_id}/groups/{group_id}/members/{rm_id}"
        )

        assert response.status_code == 204
