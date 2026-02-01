"""Tag API routes."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_tag_service
from api.v1.schemas.tag import (
    TagCreate,
    TagDetailResponse,
    TagListResponse,
    TagResponse,
    TagUpdate,
    TodoTagAttach,
    TodoTagResponse,
)
from core.rate_limit import limiter
from domain.services.tag_service import TagService

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get(
    "",
    response_model=TagListResponse,
    summary="List all tags",
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_tags(
    request: Request,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> TagListResponse:
    """Get all tags for the authenticated user, including usage counts."""
    tags_with_counts = await service.get_all_for_user(user.id)
    return TagListResponse(
        data=[
            TagResponse(
                id=item["tag"].id,
                name=item["tag"].name,
                color_hex=item["tag"].color_hex,
                created_at=item["tag"].created_at,
                usage_count=item["usage_count"],
            )
            for item in tags_with_counts
        ]
    )


@router.post(
    "",
    response_model=TagDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a tag",
    responses={
        201: {"description": "Tag created successfully"},
        409: {"description": "Tag with this name already exists"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def create_tag(
    request: Request,
    body: TagCreate,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> TagDetailResponse:
    """Create a new tag. Tag names must be unique per user."""
    tag = await service.create(
        user_id=user.id,
        name=body.name,
        color_hex=body.color_hex,
    )
    return TagDetailResponse(
        data=TagResponse(
            id=tag.id,
            name=tag.name,
            color_hex=tag.color_hex,
            created_at=tag.created_at,
            usage_count=0,
        )
    )


@router.patch(
    "/{tag_id}",
    response_model=TagDetailResponse,
    summary="Update a tag",
    responses={
        200: {"description": "Tag updated successfully"},
        404: {"description": "Tag not found"},
        409: {"description": "Tag with this name already exists"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_tag(
    request: Request,
    tag_id: UUID,
    body: TagUpdate,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> TagDetailResponse:
    """Update an existing tag's name or color."""
    tag = await service.update(
        tag_id=tag_id,
        user_id=user.id,
        name=body.name,
        color_hex=body.color_hex,
    )
    return TagDetailResponse(
        data=TagResponse(
            id=tag.id,
            name=tag.name,
            color_hex=tag.color_hex,
            created_at=tag.created_at,
            usage_count=0,
        )
    )


@router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a tag",
    responses={
        204: {"description": "Tag deleted successfully"},
        404: {"description": "Tag not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def delete_tag(
    request: Request,
    tag_id: UUID,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> None:
    """Delete a tag. Automatically detaches from all tasks."""
    await service.delete(tag_id, user.id)
    return None


# Todo-Tag relationship endpoints
todos_tags_router = APIRouter(prefix="/todos/{todo_id}/tags", tags=["todo-tags"])


@todos_tags_router.get(
    "",
    response_model=TagListResponse,
    summary="Get tags for a task",
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_todo_tags(
    request: Request,
    todo_id: UUID,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> TagListResponse:
    """Get all tags attached to a specific task."""
    tags = await service.get_tags_for_todo(todo_id, user.id)
    return TagListResponse(
        data=[
            TagResponse(
                id=tag.id,
                name=tag.name,
                color_hex=tag.color_hex,
                created_at=tag.created_at,
                usage_count=0,
            )
            for tag in tags
        ]
    )


@todos_tags_router.post(
    "",
    response_model=TodoTagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Attach a tag to a task",
    responses={
        201: {"description": "Tag attached successfully"},
        404: {"description": "Task or tag not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def attach_tag(
    request: Request,
    todo_id: UUID,
    body: TodoTagAttach,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> TodoTagResponse:
    """Attach a tag to a task. Idempotent if already attached."""
    await service.attach_to_todo(body.tag_id, todo_id, user.id)
    return TodoTagResponse(
        todo_id=todo_id,
        tag_id=body.tag_id,
        attached_at=datetime.utcnow(),
    )


@todos_tags_router.delete(
    "/{tag_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Detach a tag from a task",
    responses={
        204: {"description": "Tag detached successfully"},
        404: {"description": "Task or tag not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def detach_tag(
    request: Request,
    todo_id: UUID,
    tag_id: UUID,
    user: CurrentUser,
    service: TagService = Depends(get_tag_service),
) -> None:
    """Detach a tag from a task."""
    await service.detach_from_todo(tag_id, todo_id, user.id)
    return None
