"""Activity log API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_activity_service
from api.v1.schemas.activity import ActivityListResponse, ActivityLogResponse
from core.rate_limit import limiter
from domain.services.activity_service import ActivityService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/activity",
    tags=["activity"],
)


@router.get(
    "",
    response_model=ActivityListResponse,
    summary="Get workspace activity feed",
    responses={
        200: {"description": "Paginated activity feed"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_workspace_activity(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    service: ActivityService = Depends(get_activity_service),
) -> ActivityListResponse:
    """Get the activity feed for a workspace. Requires membership."""
    activities = await service.get_workspace_activity(
        workspace_id=workspace_id,
        user_id=user.id,
        limit=limit,
        offset=offset,
    )
    data = [
        ActivityLogResponse(
            id=a.id,
            workspace_id=a.workspace_id,
            actor_id=a.actor_id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            changes=a.changes,
            metadata=a.metadata,
            created_at=a.created_at,
        )
        for a in activities
    ]
    return ActivityListResponse(data=data, meta={"limit": limit, "offset": offset})


@router.get(
    "/{entity_type}/{entity_id}",
    response_model=ActivityListResponse,
    summary="Get entity activity history",
    responses={
        200: {"description": "Entity-specific activity history"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_entity_history(
    request: Request,
    workspace_id: UUID,
    entity_type: str,
    entity_id: UUID,
    user: CurrentUser,
    limit: int = Query(50, ge=1, le=100),
    service: ActivityService = Depends(get_activity_service),
) -> ActivityListResponse:
    """Get activity history for a specific entity. Requires membership."""
    activities = await service.get_entity_history(
        workspace_id=workspace_id,
        user_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
    )
    data = [
        ActivityLogResponse(
            id=a.id,
            workspace_id=a.workspace_id,
            actor_id=a.actor_id,
            action=a.action,
            entity_type=a.entity_type,
            entity_id=a.entity_id,
            changes=a.changes,
            metadata=a.metadata,
            created_at=a.created_at,
        )
        for a in activities
    ]
    return ActivityListResponse(data=data, meta={"limit": limit})
