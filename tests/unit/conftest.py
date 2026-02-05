"""Shared fixtures for unit tests."""

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest


class FakeUnitOfWork:
    """Fake Unit of Work with all 7 repository mocks for unit testing."""

    def __init__(self):
        self.todos = AsyncMock()
        self.tags = AsyncMock()
        self.workspaces = AsyncMock()
        self.invitations = AsyncMock()
        self.activities = AsyncMock()
        self.groups = AsyncMock()
        self.notifications = AsyncMock()
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


@pytest.fixture
def uow() -> FakeUnitOfWork:
    """Create a fresh FakeUnitOfWork."""
    return FakeUnitOfWork()


@pytest.fixture
def user_id() -> UUID:
    """A random user ID."""
    return uuid4()


@pytest.fixture
def workspace_id() -> UUID:
    """A random workspace ID."""
    return uuid4()


@pytest.fixture
def actor_id() -> UUID:
    """A random actor ID (distinct from user_id)."""
    return uuid4()
