"""Todo API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_tag_service, get_todo_service
from api.v1.schemas.todo import (
    TagSummary,
    TodoCreate,
    TodoDetailResponse,
    TodoListResponse,
    TodoResponse,
    TodoUpdate,
)
from core.rate_limit import limiter
from domain.entities.tag import Tag
from domain.entities.todo import Todo
from domain.services.tag_service import TagService
from domain.services.todo_service import TodoService

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get(
    "",
    response_model=TodoListResponse,
    summary="List all tasks",
    responses={
        200: {"description": "List of tasks with tags and metadata"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_todos(
    request: Request,
    user: CurrentUser,
    todo_service: TodoService = Depends(get_todo_service),
    tag_service: TagService = Depends(get_tag_service),
    include_completed: bool = Query(True, description="Include completed todos"),
    tag_id: UUID | None = Query(None, description="Filter by tag ID"),
    workspace_id: UUID | None = Query(None, description="Filter by workspace ID"),
) -> TodoListResponse:
    """
    Get all tasks for the authenticated user as a flat list.

    The frontend assembles the tree structure using `parent_id` references.
    Supports filtering by completion status, tag, and workspace.
    """
    todos = await todo_service.get_all_for_user(user.id, workspace_id=workspace_id)

    # Filter by completion status first
    filtered_todos = todos
    if not include_completed:
        filtered_todos = [t for t in todos if not t.is_completed]

    # Batch fetch tags and child counts for all todos (avoids N+1 queries)
    todo_ids = [t.id for t in filtered_todos]
    tags_by_todo = await tag_service.get_tags_for_todos_batch(todo_ids)
    child_counts = await todo_service.get_child_counts_batch(todo_ids)

    result = []
    for todo in filtered_todos:
        todo_tags = tags_by_todo.get(todo.id, [])

        # Filter by tag if specified
        if tag_id and not any(t.id == tag_id for t in todo_tags):
            continue

        cc, ccc = child_counts.get(todo.id, (0, 0))
        result.append(_build_todo_response(todo, todo_tags, cc, ccc))

    return TodoListResponse(
        data=result,
        meta={
            "total": len(result),
            "root_count": len([t for t in result if t.parent_id is None]),
        },
    )


@router.get(
    "/{todo_id}",
    response_model=TodoDetailResponse,
    summary="Get a task",
    responses={
        200: {"description": "Task details with tags"},
        404: {"description": "Task not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_todo(
    request: Request,
    todo_id: UUID,
    user: CurrentUser,
    todo_service: TodoService = Depends(get_todo_service),
    tag_service: TagService = Depends(get_tag_service),
) -> TodoDetailResponse:
    """Get a specific task by ID, including its tags."""
    todo = await todo_service.get_by_id(todo_id, user.id)
    tags = await tag_service.get_tags_for_todo(todo_id, user.id)
    child_counts = await todo_service.get_child_counts_batch([todo_id])
    cc, ccc = child_counts.get(todo_id, (0, 0))
    return TodoDetailResponse(data=_build_todo_response(todo, tags, cc, ccc))


@router.post(
    "",
    response_model=TodoDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new task",
    responses={
        201: {"description": "Task created successfully"},
        404: {"description": "Parent task not found"},
        422: {"description": "Validation error"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def create_todo(
    request: Request,
    body: TodoCreate,
    user: CurrentUser,
    service: TodoService = Depends(get_todo_service),
) -> TodoDetailResponse:
    """
    Create a new task for the authenticated user.

    If `parent_id` is provided, the task is created as a child of the specified parent.
    The task is automatically positioned at the end of its sibling list.
    """
    todo = await service.create(
        user_id=user.id,
        title=body.title,
        description=body.description,
        parent_id=body.parent_id,
        workspace_id=body.workspace_id,
        actor_name=user.email,
    )
    return TodoDetailResponse(data=_build_todo_response(todo, []))


@router.patch(
    "/{todo_id}",
    response_model=TodoDetailResponse,
    summary="Update a task",
    responses={
        200: {"description": "Task updated successfully"},
        400: {"description": "Circular reference detected"},
        404: {"description": "Task not found"},
        422: {"description": "Validation error"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_todo(
    request: Request,
    todo_id: UUID,
    body: TodoUpdate,
    user: CurrentUser,
    todo_service: TodoService = Depends(get_todo_service),
    tag_service: TagService = Depends(get_tag_service),
) -> TodoDetailResponse:
    """
    Update an existing task. All fields are optional (partial update).

    Set `parent_id` to `null` to move a task to the root level.
    Circular references are automatically detected and rejected.
    """
    # Handle parent_id sentinel value: only pass it if explicitly set in request
    parent_id = (
        ...
        if "parent_id" not in body.model_fields_set
        else body.parent_id
    )

    todo = await todo_service.update(
        todo_id=todo_id,
        user_id=user.id,
        title=body.title,
        description=body.description,
        is_completed=body.is_completed,
        parent_id=parent_id,
        position=body.position,
        actor_name=user.email,
    )
    tags = await tag_service.get_tags_for_todo(todo_id, user.id)
    child_counts = await todo_service.get_child_counts_batch([todo_id])
    cc, ccc = child_counts.get(todo_id, (0, 0))
    return TodoDetailResponse(data=_build_todo_response(todo, tags, cc, ccc))


@router.delete(
    "/{todo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
    responses={
        204: {"description": "Task deleted successfully"},
        404: {"description": "Task not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def delete_todo(
    request: Request,
    todo_id: UUID,
    user: CurrentUser,
    service: TodoService = Depends(get_todo_service),
) -> None:
    """Delete a task and all its descendants (cascade delete)."""
    await service.delete(todo_id, user.id, actor_name=user.email)
    return None


def _build_todo_response(
    todo: Todo, tags: list[Tag], child_count: int = 0, completed_child_count: int = 0
) -> TodoResponse:
    """Convert domain entity to response schema with tags and child counts."""
    return TodoResponse(
        id=todo.id,
        parent_id=todo.parent_id,
        workspace_id=todo.workspace_id,
        title=todo.title,
        description=todo.description,
        is_completed=todo.is_completed,
        position=todo.position,
        created_at=todo.created_at,
        updated_at=todo.updated_at,
        completed_at=todo.completed_at,
        tags=[
            TagSummary(id=t.id, name=t.name, color_hex=t.color_hex)
            for t in tags
        ],
        child_count=child_count,
        completed_child_count=completed_child_count,
    )
