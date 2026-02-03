"""Unit of Work protocol."""

from typing import Protocol

from domain.repositories.activity_repository import IActivityRepository
from domain.repositories.group_repository import IGroupRepository
from domain.repositories.todo_repository import ITodoRepository
from domain.repositories.tag_repository import ITagRepository
from domain.repositories.workspace_repository import IWorkspaceRepository
from domain.repositories.invitation_repository import IInvitationRepository


class IUnitOfWork(Protocol):
    """Unit of Work interface for managing transactions."""

    todos: ITodoRepository
    tags: ITagRepository
    workspaces: IWorkspaceRepository
    invitations: IInvitationRepository
    activities: IActivityRepository
    groups: IGroupRepository

    async def commit(self) -> None:
        """Commit the current transaction."""
        ...

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        ...

    async def __aenter__(self) -> "IUnitOfWork":
        """Enter the context manager."""
        ...

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore
        """Exit the context manager."""
        ...
