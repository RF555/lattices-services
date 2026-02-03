"""Notification API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_notification_service
from api.v1.schemas.notification import (
    MarkAllReadResponse,
    NotificationListResponse,
    NotificationPreferenceListResponse,
    NotificationPreferenceRequest,
    NotificationPreferenceResponse,
    NotificationResponse,
    NotificationTypeListResponse,
    NotificationTypeResponse,
    UnreadCountResponse,
)
from core.rate_limit import limiter
from domain.services.notification_service import NotificationService

# Workspace-scoped notification routes
workspace_notifications_router = APIRouter(
    prefix="/workspaces/{workspace_id}/notifications",
    tags=["notifications"],
)

# User-scoped notification routes
user_notifications_router = APIRouter(
    prefix="/users/me",
    tags=["notifications"],
)


# --- Workspace-scoped routes ---


@workspace_notifications_router.get(
    "",
    response_model=NotificationListResponse,
    summary="List workspace notifications",
    responses={
        200: {"description": "Paginated notification feed"},
        403: {"description": "Not a workspace member"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_workspace_notifications(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    is_read: bool | None = Query(None, description="Filter by read status"),
    cursor: UUID | None = Query(None, description="Cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """List notifications for a workspace. Requires membership."""
    notifications, unread_count = await service.get_notifications(
        user_id=user.id,
        workspace_id=workspace_id,
        is_read=is_read,
        limit=limit,
        cursor=cursor,
    )
    next_cursor = str(notifications[-1]["id"]) if notifications else None
    return NotificationListResponse(
        data=[NotificationResponse(**n) for n in notifications],
        meta={"unread_count": unread_count, "next_cursor": next_cursor},
    )


@workspace_notifications_router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    summary="Get unread notification count",
    responses={
        200: {"description": "Unread count for workspace"},
    },
)
@limiter.limit("60/minute")  # type: ignore[untyped-decorator]
async def get_workspace_unread_count(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    """Get unread notification count for a workspace."""
    count = await service.get_unread_count(user.id, workspace_id)
    return UnreadCountResponse(count=count)


@workspace_notifications_router.patch(
    "/{recipient_id}/read",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark notification as read",
    responses={
        204: {"description": "Notification marked as read"},
        404: {"description": "Notification recipient not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def mark_notification_read(
    request: Request,
    workspace_id: UUID,
    recipient_id: UUID,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Mark a notification as read. Requires recipient ownership."""
    await service.mark_read(recipient_id, user.id)


@workspace_notifications_router.patch(
    "/{recipient_id}/unread",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Mark notification as unread",
    responses={
        204: {"description": "Notification marked as unread"},
        404: {"description": "Notification recipient not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def mark_notification_unread(
    request: Request,
    workspace_id: UUID,
    recipient_id: UUID,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Mark a notification as unread. Requires recipient ownership."""
    await service.mark_unread(recipient_id, user.id)


@workspace_notifications_router.post(
    "/mark-all-read",
    response_model=MarkAllReadResponse,
    summary="Mark all workspace notifications as read",
    responses={
        200: {"description": "Count of notifications marked as read"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def mark_all_workspace_notifications_read(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    """Mark all notifications as read for a workspace."""
    count = await service.mark_all_read(user.id, workspace_id)
    return MarkAllReadResponse(count=count)


@workspace_notifications_router.delete(
    "/{recipient_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete notification",
    responses={
        204: {"description": "Notification soft-deleted"},
        404: {"description": "Notification recipient not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def delete_notification(
    request: Request,
    workspace_id: UUID,
    recipient_id: UUID,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> None:
    """Soft-delete a notification. Requires recipient ownership."""
    await service.delete_notification(recipient_id, user.id)


# --- User-scoped routes ---


@user_notifications_router.get(
    "/notifications",
    response_model=NotificationListResponse,
    summary="List all notifications (cross-workspace)",
    responses={
        200: {"description": "Cross-workspace notification feed"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_user_notifications(
    request: Request,
    user: CurrentUser,
    is_read: bool | None = Query(None, description="Filter by read status"),
    cursor: UUID | None = Query(None, description="Cursor for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Page size"),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """List all notifications across all workspaces."""
    notifications, unread_count = await service.get_notifications(
        user_id=user.id,
        is_read=is_read,
        limit=limit,
        cursor=cursor,
    )
    next_cursor = str(notifications[-1]["id"]) if notifications else None
    return NotificationListResponse(
        data=[NotificationResponse(**n) for n in notifications],
        meta={"unread_count": unread_count, "next_cursor": next_cursor},
    )


@user_notifications_router.get(
    "/notifications/unread-count",
    response_model=UnreadCountResponse,
    summary="Get total unread count (cross-workspace)",
    responses={
        200: {"description": "Total unread notification count"},
    },
)
@limiter.limit("60/minute")  # type: ignore[untyped-decorator]
async def get_user_unread_count(
    request: Request,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    """Get total unread notification count across all workspaces."""
    count = await service.get_unread_count(user.id)
    return UnreadCountResponse(count=count)


@user_notifications_router.post(
    "/notifications/mark-all-read",
    response_model=MarkAllReadResponse,
    summary="Mark all notifications as read (cross-workspace)",
    responses={
        200: {"description": "Count of notifications marked as read"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def mark_all_user_notifications_read(
    request: Request,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> MarkAllReadResponse:
    """Mark all notifications as read across all workspaces."""
    count = await service.mark_all_read(user.id)
    return MarkAllReadResponse(count=count)


@user_notifications_router.get(
    "/notification-preferences",
    response_model=NotificationPreferenceListResponse,
    summary="Get notification preferences",
    responses={
        200: {"description": "User's notification preferences"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_notification_preferences(
    request: Request,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceListResponse:
    """Get all notification preferences for the current user."""
    prefs = await service.get_preferences(user.id)
    return NotificationPreferenceListResponse(
        data=[
            NotificationPreferenceResponse(
                id=p.id,
                channel=p.channel,
                enabled=p.enabled,
                workspace_id=p.workspace_id,
                notification_type=p.notification_type,
            )
            for p in prefs
        ]
    )


@user_notifications_router.put(
    "/notification-preferences",
    response_model=NotificationPreferenceResponse,
    summary="Update notification preference",
    responses={
        200: {"description": "Preference created or updated"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_notification_preference(
    request: Request,
    body: NotificationPreferenceRequest,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationPreferenceResponse:
    """Create or update a notification preference."""
    pref = await service.update_preference(
        user_id=user.id,
        channel=body.channel,
        enabled=body.enabled,
        workspace_id=body.workspace_id,
        notification_type=body.notification_type,
    )
    return NotificationPreferenceResponse(
        id=pref.id,
        channel=pref.channel,
        enabled=pref.enabled,
        workspace_id=pref.workspace_id,
        notification_type=pref.notification_type,
    )


@user_notifications_router.get(
    "/notification-types",
    response_model=NotificationTypeListResponse,
    summary="List notification types",
    responses={
        200: {"description": "All available notification types"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_notification_types(
    request: Request,
    user: CurrentUser,
    service: NotificationService = Depends(get_notification_service),
) -> NotificationTypeListResponse:
    """Get all available notification types (for preferences UI)."""
    types = await service.get_notification_types()
    return NotificationTypeListResponse(
        data=[
            NotificationTypeResponse(
                name=t.name,
                description=t.description,
                template=t.template,
                is_mandatory=t.is_mandatory,
            )
            for t in types
        ]
    )
