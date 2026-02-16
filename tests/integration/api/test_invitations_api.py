"""Integration tests for Invitations API."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser
from infrastructure.database.models import ProfileModel


@pytest.fixture
async def invitation_client(
    session_factory: async_sessionmaker[AsyncSession],
    test_user: TokenUser,
    auth_provider: JWTAuthProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client with invitation services wired up."""
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
    app.dependency_overrides[get_invitation_service] = lambda: InvitationService(test_uow_factory)
    app.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
    app.dependency_overrides[get_activity_service] = lambda: activity_service
    app.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
    app.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def inv_workspace_id(invitation_client: AsyncClient) -> str:
    """Create a workspace for invitation tests."""
    unique_name = f"Invitation Test WS {uuid4().hex[:8]}"
    response = await invitation_client.post("/api/v1/workspaces", json={"name": unique_name})
    assert response.status_code == 201, f"Workspace creation failed: {response.json()}"
    return str(response.json()["data"]["id"])


class TestInvitationCreation:
    """Tests for creating invitations."""

    @pytest.mark.asyncio
    async def test_create_invitation(
        self, invitation_client: AsyncClient, inv_workspace_id: str
    ) -> None:
        """POST /api/v1/workspaces/{ws}/invitations returns 201 with token."""
        response = await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": "invitee@example.com", "role": "member"},
        )

        assert response.status_code == 201
        data = response.json()
        assert "token" in data
        assert data["data"]["email"] == "invitee@example.com"
        assert data["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_duplicate_invitation(
        self, invitation_client: AsyncClient, inv_workspace_id: str
    ) -> None:
        """Creating duplicate invitation for same email returns 409."""
        email = f"dup-inv-{uuid4()}@example.com"

        await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": email, "role": "member"},
        )

        response = await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": email, "role": "member"},
        )

        assert response.status_code == 409


class TestInvitationListing:
    """Tests for listing invitations."""

    @pytest.mark.asyncio
    async def test_list_workspace_invitations(
        self, invitation_client: AsyncClient, inv_workspace_id: str
    ) -> None:
        """GET /api/v1/workspaces/{ws}/invitations returns list."""
        await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": f"list-{uuid4()}@example.com", "role": "member"},
        )

        response = await invitation_client.get(f"/api/v1/workspaces/{inv_workspace_id}/invitations")

        assert response.status_code == 200
        assert len(response.json()["data"]) >= 1

    @pytest.mark.asyncio
    async def test_get_pending_invitations(self, invitation_client: AsyncClient) -> None:
        """GET /api/v1/invitations/pending returns user's pending invitations."""
        response = await invitation_client.get("/api/v1/invitations/pending")

        assert response.status_code == 200
        assert "data" in response.json()


class TestInvitationAccept:
    """Tests for accepting invitations."""

    @pytest.mark.asyncio
    async def test_accept_invitation_full_flow(
        self,
        invitation_client: AsyncClient,
        inv_workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: TokenUser,
        auth_provider: JWTAuthProvider,
    ) -> None:
        """Full accept flow: create invite, accept with matching email user."""
        # Create invitation for test user's email
        create_resp = await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": "acceptee@example.com", "role": "member"},
        )
        token = create_resp.json()["token"]

        # Create a second user that matches the invitation email
        second_user_id = uuid4()
        second_user = TokenUser(
            id=second_user_id,
            email="acceptee@example.com",
            display_name="Acceptee",
        )
        async with session_factory() as session:
            profile = ProfileModel(
                id=second_user_id,
                email="acceptee@example.com",
                display_name="Acceptee",
            )
            session.add(profile)
            await session.commit()

        # Create a second client authenticated as the acceptee
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

        app2 = create_app()

        async def override_get_user2() -> TokenUser:
            return second_user

        def test_uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(session_factory)

        activity_service = ActivityService(test_uow_factory)

        app2.dependency_overrides[get_current_user] = override_get_user2
        app2.dependency_overrides[get_auth_provider] = lambda: auth_provider
        app2.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app2.dependency_overrides[get_invitation_service] = lambda: InvitationService(
            test_uow_factory
        )
        app2.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
        app2.dependency_overrides[get_activity_service] = lambda: activity_service
        app2.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
        app2.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

        transport2 = ASGITransport(app=app2)
        async with AsyncClient(transport=transport2, base_url="http://test") as c2:
            response = await c2.post(
                "/api/v1/invitations/accept",
                json={"token": token},
            )

        assert response.status_code == 200
        assert response.json()["workspace_id"] == inv_workspace_id

        app2.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_accept_by_id_full_flow(
        self,
        invitation_client: AsyncClient,
        inv_workspace_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        test_user: TokenUser,
        auth_provider: JWTAuthProvider,
    ) -> None:
        """Full accept-by-ID flow: create invite, accept by invitation ID."""
        # Create invitation for a specific email
        create_resp = await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": "id-acceptee@example.com", "role": "member"},
        )
        invitation_id = create_resp.json()["data"]["id"]

        # Create a second user that matches the invitation email
        second_user_id = uuid4()
        second_user = TokenUser(
            id=second_user_id,
            email="id-acceptee@example.com",
            display_name="ID Acceptee",
        )
        async with session_factory() as session:
            profile = ProfileModel(
                id=second_user_id,
                email="id-acceptee@example.com",
                display_name="ID Acceptee",
            )
            session.add(profile)
            await session.commit()

        # Create a second client authenticated as the acceptee
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

        app2 = create_app()

        async def override_get_user2() -> TokenUser:
            return second_user

        def test_uow_factory() -> SQLAlchemyUnitOfWork:
            return SQLAlchemyUnitOfWork(session_factory)

        activity_service = ActivityService(test_uow_factory)

        app2.dependency_overrides[get_current_user] = override_get_user2
        app2.dependency_overrides[get_auth_provider] = lambda: auth_provider
        app2.dependency_overrides[get_workspace_service] = lambda: WorkspaceService(
            test_uow_factory, activity_service=activity_service
        )
        app2.dependency_overrides[get_invitation_service] = lambda: InvitationService(
            test_uow_factory
        )
        app2.dependency_overrides[get_group_service] = lambda: GroupService(test_uow_factory)
        app2.dependency_overrides[get_activity_service] = lambda: activity_service
        app2.dependency_overrides[get_todo_service] = lambda: TodoService(test_uow_factory)
        app2.dependency_overrides[get_tag_service] = lambda: TagService(test_uow_factory)

        transport2 = ASGITransport(app=app2)
        async with AsyncClient(transport=transport2, base_url="http://test") as c2:
            response = await c2.post(f"/api/v1/invitations/{invitation_id}/accept")

        assert response.status_code == 200
        assert response.json()["workspace_id"] == inv_workspace_id

        app2.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_accept_by_id_nonexistent(self, invitation_client: AsyncClient) -> None:
        """Accepting with non-existent invitation ID returns 404."""
        response = await invitation_client.post(
            f"/api/v1/invitations/{uuid4()}/accept",
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_accept_with_invalid_token(self, invitation_client: AsyncClient) -> None:
        """Accepting with bad token returns 404."""
        response = await invitation_client.post(
            "/api/v1/invitations/accept",
            json={"token": "invalid-token-abc123"},
        )

        assert response.status_code == 404


class TestInvitationRevoke:
    """Tests for revoking invitations."""

    @pytest.mark.asyncio
    async def test_revoke_invitation(
        self, invitation_client: AsyncClient, inv_workspace_id: str
    ) -> None:
        """DELETE /api/v1/workspaces/{ws}/invitations/{id} revokes invitation."""
        create_resp = await invitation_client.post(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations",
            json={"email": f"revoke-{uuid4()}@example.com", "role": "member"},
        )
        invitation_id = create_resp.json()["data"]["id"]

        response = await invitation_client.delete(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations/{invitation_id}"
        )

        assert response.status_code == 204

    @pytest.mark.asyncio
    async def test_revoke_nonexistent(
        self, invitation_client: AsyncClient, inv_workspace_id: str
    ) -> None:
        """Revoking nonexistent invitation returns 404."""
        response = await invitation_client.delete(
            f"/api/v1/workspaces/{inv_workspace_id}/invitations/{uuid4()}"
        )

        assert response.status_code == 404
