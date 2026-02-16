"""Integration tests for Workspaces API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser
from infrastructure.database.models import ProfileModel


@pytest.fixture
async def workspace_client(
    session_factory: async_sessionmaker[AsyncSession],
    test_user: TokenUser,
    auth_provider: JWTAuthProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with all workspace-related services wired up."""
    from api.dependencies.auth import get_auth_provider, get_current_user, get_workspace_service_dep
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
    app.dependency_overrides[get_workspace_service_dep] = lambda: WorkspaceService(
        test_uow_factory, activity_service=activity_service
    )
    app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
        test_uow_factory, activity_service=activity_service
    )
    app.dependency_overrides[get_invitation_service] = lambda: InvitationService(test_uow_factory)
    app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
    app.dependency_overrides[get_activity_service] = lambda: activity_service
    app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
    app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


def _unique_name(prefix: str) -> str:
    """Generate a unique workspace name to avoid slug collisions."""
    return f"{prefix} {uuid4().hex[:8]}"


class TestWorkspaceCRUD:
    """Tests for workspace create, read, update, delete."""

    @pytest.mark.asyncio
    async def test_create_workspace(self, workspace_client: AsyncClient) -> None:
        """POST /api/v1/workspaces returns 201 with workspace data."""
        name = _unique_name("Create WS")
        response = await workspace_client.post(
            "/api/v1/workspaces",
            json={"name": name, "description": "A test workspace"},
        )

        assert response.status_code == 201
        data = response.json()["data"]
        assert data["name"] == name
        assert "id" in data
        assert data["slug"]  # slug is generated

    @pytest.mark.asyncio
    async def test_list_workspaces(self, workspace_client: AsyncClient) -> None:
        """GET /api/v1/workspaces returns list of user's workspaces."""
        await workspace_client.post("/api/v1/workspaces", json={"name": _unique_name("List WS")})

        response = await workspace_client.get("/api/v1/workspaces")

        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    @pytest.mark.asyncio
    async def test_get_workspace(self, workspace_client: AsyncClient) -> None:
        """GET /api/v1/workspaces/{id} returns workspace details."""
        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Get WS")}
        )
        ws_id = create.json()["data"]["id"]

        response = await workspace_client.get(f"/api/v1/workspaces/{ws_id}")

        assert response.status_code == 200
        assert response.json()["data"]["id"] == ws_id

    @pytest.mark.asyncio
    async def test_get_workspace_not_found(self, workspace_client: AsyncClient) -> None:
        """GET /api/v1/workspaces/{id} returns 404 for unknown workspace."""
        response = await workspace_client.get(f"/api/v1/workspaces/{uuid4()}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workspace(self, workspace_client: AsyncClient) -> None:
        """PATCH /api/v1/workspaces/{id} updates workspace."""
        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Update WS")}
        )
        ws_id = create.json()["data"]["id"]

        new_name = _unique_name("Updated WS")
        response = await workspace_client.patch(
            f"/api/v1/workspaces/{ws_id}",
            json={"name": new_name},
        )

        assert response.status_code == 200
        assert response.json()["data"]["name"] == new_name

    @pytest.mark.asyncio
    async def test_delete_workspace(self, workspace_client: AsyncClient) -> None:
        """DELETE /api/v1/workspaces/{id} returns 204."""
        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Delete WS")}
        )
        ws_id = create.json()["data"]["id"]

        response = await workspace_client.delete(f"/api/v1/workspaces/{ws_id}")

        assert response.status_code == 204

        # Verify deleted
        get_resp = await workspace_client.get(f"/api/v1/workspaces/{ws_id}")
        assert get_resp.status_code == 404


class TestWorkspaceMembers:
    """Tests for workspace member management."""

    @pytest.mark.asyncio
    async def test_list_members(self, workspace_client: AsyncClient) -> None:
        """GET /api/v1/workspaces/{id}/members includes the owner."""
        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Members WS")}
        )
        ws_id = create.json()["data"]["id"]

        response = await workspace_client.get(f"/api/v1/workspaces/{ws_id}/members")

        assert response.status_code == 200
        members = response.json()["data"]
        assert len(members) >= 1
        roles = [m["role"] for m in members]
        assert "owner" in roles

    @pytest.mark.asyncio
    async def test_add_member(
        self, workspace_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """POST /api/v1/workspaces/{id}/members adds a new member."""
        second_user_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=second_user_id,
                email=f"ws-add-{second_user_id}@example.com",
                display_name="Second User",
            )
            session.add(profile)
            await session.commit()

        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Add Member WS")}
        )
        ws_id = create.json()["data"]["id"]

        response = await workspace_client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"user_id": str(second_user_id), "role": "member"},
        )

        assert response.status_code == 201
        assert response.json()["role"] == "member"

    @pytest.mark.asyncio
    async def test_add_member_duplicate(
        self, workspace_client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
    ) -> None:
        """POST /api/v1/workspaces/{id}/members returns 409 for duplicate."""
        dup_user_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=dup_user_id,
                email=f"ws-dup-{dup_user_id}@example.com",
                display_name="Dup User",
            )
            session.add(profile)
            await session.commit()

        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Dup Member WS")}
        )
        ws_id = create.json()["data"]["id"]

        await workspace_client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"user_id": str(dup_user_id), "role": "member"},
        )

        response = await workspace_client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"user_id": str(dup_user_id), "role": "member"},
        )

        assert response.status_code == 409


class TestWorkspaceOwnership:
    """Tests for workspace ownership operations."""

    @pytest.mark.asyncio
    async def test_transfer_ownership(
        self,
        workspace_client: AsyncClient,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /api/v1/workspaces/{id}/transfer-ownership succeeds for owner."""
        target_id = uuid4()
        async with session_factory() as session:
            profile = ProfileModel(
                id=target_id,
                email=f"ws-transfer-{target_id}@example.com",
                display_name="Transfer Target",
            )
            session.add(profile)
            await session.commit()

        create = await workspace_client.post(
            "/api/v1/workspaces", json={"name": _unique_name("Transfer WS")}
        )
        ws_id = create.json()["data"]["id"]

        await workspace_client.post(
            f"/api/v1/workspaces/{ws_id}/members",
            json={"user_id": str(target_id), "role": "admin"},
        )

        response = await workspace_client.post(
            f"/api/v1/workspaces/{ws_id}/transfer-ownership",
            json={"new_owner_id": str(target_id)},
        )

        assert response.status_code == 204


class TestAutoProvisionPersonalWorkspace:
    """Tests for automatic personal workspace provisioning."""

    @pytest.mark.asyncio
    async def test_auto_creates_personal_workspace_for_new_user(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        auth_provider: JWTAuthProvider,
    ) -> None:
        """GET /api/v1/workspaces for a fresh user auto-creates a Personal workspace."""
        from api.dependencies.auth import (
            get_auth_provider,
            get_current_user,
            get_workspace_service_dep,
        )
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

        # Create a brand-new user with no workspaces
        fresh_user_id = uuid4()
        fresh_user = TokenUser(
            id=fresh_user_id,
            email=f"fresh-{fresh_user_id}@example.com",
            display_name="Fresh User",
        )

        async with session_factory() as session:
            profile = ProfileModel(
                id=fresh_user.id,
                email=fresh_user.email,
                display_name=fresh_user.display_name,
            )
            session.add(profile)
            await session.commit()

        app = create_app()

        async def override_get_user() -> TokenUser:
            return fresh_user

        def test_uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(session_factory)

        activity_service = ActivityService(test_uow_factory)

        app.dependency_overrides[get_current_user] = override_get_user
        app.dependency_overrides[get_auth_provider] = lambda: auth_provider
        app.dependency_overrides[get_workspace_service_dep] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_invitation_service] = lambda: InvitationService(
            test_uow_factory
        )
        app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
        app.dependency_overrides[get_activity_service] = lambda: activity_service
        app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
        app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First request — should auto-create "Personal" workspace
            response = await client.get("/api/v1/workspaces")

            assert response.status_code == 200
            data = response.json()["data"]
            assert len(data) == 1
            assert data[0]["name"] == "Personal"
            assert data[0]["slug"].startswith("personal-")

            # Second request — should be idempotent (still 1 workspace)
            response2 = await client.get("/api/v1/workspaces")
            assert len(response2.json()["data"]) == 1

        app.dependency_overrides.clear()


class TestLastWorkspaceGuard:
    """Tests for preventing deletion/leaving of last workspace."""

    @pytest.mark.asyncio
    async def test_delete_last_workspace_returns_400(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        auth_provider: JWTAuthProvider,
    ) -> None:
        """DELETE /api/v1/workspaces/{id} returns 400 when it's the user's only workspace."""
        from api.dependencies.auth import (
            get_auth_provider,
            get_current_user,
            get_workspace_service_dep,
        )
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

        # Use a fresh user to have exactly 1 workspace
        fresh_user_id = uuid4()
        fresh_user = TokenUser(
            id=fresh_user_id,
            email=f"delete-guard-{fresh_user_id}@example.com",
            display_name="Delete Guard User",
        )
        async with session_factory() as session:
            profile = ProfileModel(
                id=fresh_user.id, email=fresh_user.email, display_name=fresh_user.display_name
            )
            session.add(profile)
            await session.commit()

        app = create_app()

        async def override_get_user() -> TokenUser:
            return fresh_user

        def test_uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(session_factory)

        activity_service = ActivityService(test_uow_factory)

        app.dependency_overrides[get_current_user] = override_get_user
        app.dependency_overrides[get_auth_provider] = lambda: auth_provider
        app.dependency_overrides[get_workspace_service_dep] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_invitation_service] = lambda: InvitationService(
            test_uow_factory
        )
        app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
        app.dependency_overrides[get_activity_service] = lambda: activity_service
        app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
        app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create exactly one workspace for this user
            create = await client.post("/api/v1/workspaces", json={"name": _unique_name("Only WS")})
            assert create.status_code == 201
            ws_id = create.json()["data"]["id"]

            # Attempt to delete it — should fail
            response = await client.delete(f"/api/v1/workspaces/{ws_id}")
            assert response.status_code == 400
            assert response.json()["error_code"] == "LAST_WORKSPACE"

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_leave_last_workspace_returns_400(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        auth_provider: JWTAuthProvider,
    ) -> None:
        """DELETE /api/v1/workspaces/{id}/members/{self} returns 400 when last workspace."""
        from api.dependencies.auth import (
            get_auth_provider,
            get_current_user,
            get_workspace_service_dep,
        )
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

        # Use a fresh user to have exactly 1 workspace
        fresh_user_id = uuid4()
        fresh_user = TokenUser(
            id=fresh_user_id,
            email=f"leave-guard-{fresh_user_id}@example.com",
            display_name="Leave Guard User",
        )
        async with session_factory() as session:
            profile = ProfileModel(
                id=fresh_user.id, email=fresh_user.email, display_name=fresh_user.display_name
            )
            session.add(profile)
            await session.commit()

        app = create_app()

        async def override_get_user() -> TokenUser:
            return fresh_user

        def test_uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(session_factory)

        activity_service = ActivityService(test_uow_factory)

        app.dependency_overrides[get_current_user] = override_get_user
        app.dependency_overrides[get_auth_provider] = lambda: auth_provider
        app.dependency_overrides[get_workspace_service_dep] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app.dependency_overrides[get_invitation_service] = lambda: InvitationService(
            test_uow_factory
        )
        app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
        app.dependency_overrides[get_activity_service] = lambda: activity_service
        app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
        app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Create exactly one workspace for this user
            create = await client.post(
                "/api/v1/workspaces", json={"name": _unique_name("Only Leave WS")}
            )
            assert create.status_code == 201
            ws_id = create.json()["data"]["id"]

            # Attempt to leave it — should fail
            response = await client.delete(f"/api/v1/workspaces/{ws_id}/members/{fresh_user.id}")
            assert response.status_code == 400
            assert response.json()["error_code"] == "LAST_WORKSPACE"

        app.dependency_overrides.clear()
