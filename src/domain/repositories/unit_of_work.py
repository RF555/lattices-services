"""Unit of Work protocol."""

from typing import Protocol

from domain.repositories.todo_repository import ITodoRepository
from domain.repositories.tag_repository import ITagRepository


class IUnitOfWork(Protocol):
    """Unit of Work interface for managing transactions."""

    todos: ITodoRepository
    tags: ITagRepository

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
