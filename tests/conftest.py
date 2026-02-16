"""Pytest configuration and fixtures."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any
from uuid import uuid4

# Disable rate limiting in tests
os.environ["RATE_LIMIT_ENABLED"] = "false"

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser
from infrastructure.database.models import Base, ProfileModel


# Compile JSONB as JSON for SQLite (used in tests)
@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(type_: Any, compiler: Any, **kw: Any) -> str:
    return "JSON"


# Test database URL (SQLite in memory)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Fixed test user ID for consistency
TEST_USER_ID = uuid4()


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for session-scoped async fixtures."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        echo=False,
    )
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
async def setup_database(engine: AsyncEngine) -> AsyncGenerator[None, None]:
    """Create all tables once per session."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="session")
async def session_factory(
    engine: AsyncEngine, setup_database: None
) -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """Create session factory."""
    factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    yield factory


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test."""
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def test_user() -> TokenUser:
    """Create a test user with fixed ID."""
    return TokenUser(
        id=TEST_USER_ID,
        email="test@example.com",
        display_name="Test User",
    )


@pytest.fixture
def auth_provider() -> JWTAuthProvider:
    """Create auth provider for testing."""
    return JWTAuthProvider(
        secret_key="test-secret-key",
        algorithm="HS256",
        expire_minutes=30,
    )


@pytest.fixture
def auth_token(auth_provider: JWTAuthProvider, test_user: TokenUser) -> str:
    """Create auth token for test user."""
    return str(auth_provider.create_token(test_user))


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    """Create authorization headers."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create async test client (no auth)."""
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def authenticated_client(
    session_factory: async_sessionmaker[AsyncSession],
    test_user: TokenUser,
    auth_provider: JWTAuthProvider,
) -> AsyncGenerator[AsyncClient, None]:
    """
    Create authenticated test client with proper database and auth overrides.

    This client:
    - Uses an in-memory SQLite database
    - Injects a test user profile into the database
    - Overrides auth dependency to return the test user
    - Overrides UoW factory to use test session
    """
    from api.dependencies.auth import get_auth_provider, get_current_user, get_workspace_service_dep
    from api.v1.dependencies import get_tag_service, get_todo_service
    from domain.services.tag_service import TagService
    from domain.services.todo_service import TodoService
    from domain.services.workspace_service import WorkspaceService
    from infrastructure.database.sqlalchemy_uow import SQLAlchemyUnitOfWork
    from main import create_app

    app = create_app()

    # Create a profile for the test user
    async with session_factory() as session:
        # Check if profile already exists
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

    # Override auth to return test user directly
    async def override_get_user() -> TokenUser:
        return test_user

    def override_get_auth_provider() -> JWTAuthProvider:
        return auth_provider

    # Create a UoW factory that uses test session
    def test_uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(session_factory)

    def override_get_todo_service() -> TodoService:
        return TodoService(test_uow_factory)

    def override_get_tag_service() -> TagService:
        return TagService(test_uow_factory)

    def override_get_workspace_service_dep() -> WorkspaceService:
        return WorkspaceService(test_uow_factory)

    app.dependency_overrides[get_current_user] = override_get_user
    app.dependency_overrides[get_auth_provider] = override_get_auth_provider
    app.dependency_overrides[get_todo_service] = override_get_todo_service
    app.dependency_overrides[get_tag_service] = override_get_tag_service
    app.dependency_overrides[get_workspace_service_dep] = override_get_workspace_service_dep

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
