"""Dependency injection factories for API v1."""

from functools import lru_cache

from domain.services.tag_service import TagService
from domain.services.todo_service import TodoService
from infrastructure.database.session import async_session_factory
from infrastructure.database.sqlalchemy_uow import SQLAlchemyUnitOfWork


def get_uow_factory():
    """Factory for creating Unit of Work instances."""

    def factory():
        return SQLAlchemyUnitOfWork(async_session_factory)

    return factory


@lru_cache
def get_todo_service() -> TodoService:
    """Get Todo service instance."""
    return TodoService(get_uow_factory())


@lru_cache
def get_tag_service() -> TagService:
    """Get Tag service instance."""
    return TagService(get_uow_factory())
