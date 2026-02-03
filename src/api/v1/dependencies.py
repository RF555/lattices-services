"""Dependency injection factories for API v1."""

from functools import lru_cache
from typing import Callable

from domain.services.activity_service import ActivityService
from domain.services.group_service import GroupService
from domain.services.invitation_service import InvitationService
from domain.services.notification_service import NotificationService
from domain.services.tag_service import TagService
from domain.services.todo_service import TodoService
from domain.services.workspace_service import WorkspaceService
from infrastructure.database.session import async_session_factory
from infrastructure.database.sqlalchemy_uow import SQLAlchemyUnitOfWork


def get_uow_factory() -> Callable[[], SQLAlchemyUnitOfWork]:
    """Factory for creating Unit of Work instances."""

    def factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(async_session_factory)

    return factory


@lru_cache
def get_activity_service() -> ActivityService:
    """Get Activity service instance."""
    return ActivityService(get_uow_factory())


@lru_cache
def get_notification_service() -> NotificationService:
    """Get Notification service instance."""
    return NotificationService(get_uow_factory())


@lru_cache
def get_todo_service() -> TodoService:
    """Get Todo service instance."""
    return TodoService(
        get_uow_factory(),
        activity_service=get_activity_service(),
        notification_service=get_notification_service(),
    )


@lru_cache
def get_tag_service() -> TagService:
    """Get Tag service instance."""
    return TagService(get_uow_factory())


@lru_cache
def get_workspace_service() -> WorkspaceService:
    """Get Workspace service instance."""
    return WorkspaceService(
        get_uow_factory(),
        activity_service=get_activity_service(),
        notification_service=get_notification_service(),
    )


@lru_cache
def get_invitation_service() -> InvitationService:
    """Get Invitation service instance."""
    return InvitationService(
        get_uow_factory(),
        notification_service=get_notification_service(),
    )


@lru_cache
def get_group_service() -> GroupService:
    """Get Group service instance."""
    return GroupService(
        get_uow_factory(),
        notification_service=get_notification_service(),
    )
