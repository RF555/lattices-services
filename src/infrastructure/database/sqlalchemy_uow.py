"""SQLAlchemy Unit of Work implementation."""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from infrastructure.database.repositories.sqlalchemy_activity_repo import SQLAlchemyActivityRepository
from infrastructure.database.repositories.sqlalchemy_group_repo import SQLAlchemyGroupRepository
from infrastructure.database.repositories.sqlalchemy_todo_repo import SQLAlchemyTodoRepository
from infrastructure.database.repositories.sqlalchemy_tag_repo import SQLAlchemyTagRepository
from infrastructure.database.repositories.sqlalchemy_invitation_repo import SQLAlchemyInvitationRepository
from infrastructure.database.repositories.sqlalchemy_workspace_repo import SQLAlchemyWorkspaceRepository


class SQLAlchemyUnitOfWork:
    """Unit of Work implementation using SQLAlchemy."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: Optional[AsyncSession] = None

    @property
    def todos(self) -> SQLAlchemyTodoRepository:
        """Get todo repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyTodoRepository(self._session)

    @property
    def tags(self) -> SQLAlchemyTagRepository:
        """Get tag repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyTagRepository(self._session)

    @property
    def invitations(self) -> SQLAlchemyInvitationRepository:
        """Get invitation repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyInvitationRepository(self._session)

    @property
    def activities(self) -> SQLAlchemyActivityRepository:
        """Get activity log repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyActivityRepository(self._session)

    @property
    def groups(self) -> SQLAlchemyGroupRepository:
        """Get group repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyGroupRepository(self._session)

    @property
    def workspaces(self) -> SQLAlchemyWorkspaceRepository:
        """Get workspace repository."""
        if not self._session:
            raise RuntimeError("UnitOfWork not initialized. Use as context manager.")
        return SQLAlchemyWorkspaceRepository(self._session)

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._session:
            await self._session.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        if self._session:
            await self._session.rollback()

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        """Enter the context manager and create session."""
        self._session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[Exception],
        exc_tb: Any,
    ) -> None:
        """Exit the context manager and cleanup."""
        if self._session:
            if exc_type:
                await self.rollback()
            await self._session.close()
            self._session = None
