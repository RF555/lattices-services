"""Todo service layer with business logic."""

from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple, cast
from uuid import UUID

from core.exceptions import (
    AppException,
    ErrorCode,
    InsufficientPermissionsError,
    NotAMemberError,
    TodoNotFoundError,
)
from domain.entities.activity import Actions
from domain.entities.todo import Todo
from domain.entities.workspace import WorkspaceRole, has_permission
from domain.repositories.unit_of_work import IUnitOfWork
from domain.services.activity_service import ActivityService


class TodoService:
    """Service layer for Todo business logic."""

    def __init__(
        self,
        uow_factory: Callable[[], IUnitOfWork],
        activity_service: Optional["ActivityService"] = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._activity = activity_service

    async def get_child_counts_batch(
        self, todo_ids: List[UUID]
    ) -> Dict[UUID, Tuple[int, int]]:
        """Get child counts for multiple todos.

        Returns a mapping of parent_id -> (child_count, completed_child_count).
        """
        if not todo_ids:
            return {}
        async with self._uow_factory() as uow:
            return await uow.todos.get_child_counts_batch(todo_ids)  # type: ignore[no-any-return]

    async def get_all_for_user(
        self, user_id: UUID, workspace_id: Optional[UUID] = None
    ) -> List[Todo]:
        """Get all todos for a user, optionally scoped to a workspace.

        If workspace_id is provided, verifies membership and returns workspace todos.
        If not, returns todos from all user workspaces (backward compatible).
        """
        async with self._uow_factory() as uow:
            if workspace_id:
                await self._require_workspace_role(
                    uow, workspace_id, user_id, WorkspaceRole.VIEWER
                )
                return await uow.todos.get_all_for_workspace(workspace_id)
            return await uow.todos.get_all_for_user(user_id)  # type: ignore[no-any-return]

    async def get_by_id(
        self, todo_id: UUID, user_id: UUID, workspace_id: Optional[UUID] = None
    ) -> Todo:
        """Get a specific todo, ensuring workspace membership or user ownership."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)
            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # If workspace_id is given, verify membership
            if workspace_id:
                await self._require_workspace_role(
                    uow, workspace_id, user_id, WorkspaceRole.VIEWER
                )
                if todo.workspace_id != workspace_id:
                    raise TodoNotFoundError(str(todo_id))
            elif todo.workspace_id:
                # Verify user has access to the todo's workspace
                member = await uow.workspaces.get_member(todo.workspace_id, user_id)
                if not member:
                    raise TodoNotFoundError(str(todo_id))
            elif todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            return todo

    async def create(
        self,
        user_id: UUID,
        title: str,
        description: Optional[str] = None,
        parent_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
    ) -> Todo:
        """Create a new todo. Requires Member+ role if workspace_id is provided."""
        async with self._uow_factory() as uow:
            if workspace_id:
                await self._require_workspace_role(
                    uow, workspace_id, user_id, WorkspaceRole.MEMBER
                )

            # Validate parent exists and user has access
            if parent_id:
                parent = await uow.todos.get(parent_id)
                if not parent:
                    raise TodoNotFoundError(str(parent_id))
                # If workspace-scoped, parent must be in same workspace
                if workspace_id and parent.workspace_id != workspace_id:
                    raise TodoNotFoundError(str(parent_id))
                elif not workspace_id and parent.user_id != user_id:
                    raise TodoNotFoundError(str(parent_id))

            # Get position for new todo (last in list)
            if parent_id:
                siblings = await uow.todos.get_children(parent_id)
            else:
                siblings = await uow.todos.get_root_todos(user_id)
            position = len(siblings)

            todo = Todo(
                user_id=user_id,
                parent_id=parent_id,
                workspace_id=workspace_id,
                title=title,
                description=description,
                position=position,
            )

            created = await uow.todos.create(todo)

            # Log activity if workspace-scoped
            if workspace_id and self._activity:
                await self._activity.log(
                    uow=uow,
                    workspace_id=workspace_id,
                    actor_id=user_id,
                    action=Actions.TODO_CREATED,
                    entity_type="todo",
                    entity_id=created.id,
                    metadata={"title": created.title},
                )

            await uow.commit()

            return created

    async def update(
        self,
        todo_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_completed: Optional[bool] = None,
        parent_id: object = ...,  # Sentinel to detect explicit None
        position: Optional[int] = None,
    ) -> Todo:
        """Update an existing todo."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)

            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # Verify access via workspace membership or user ownership
            if todo.workspace_id:
                await self._require_workspace_role(
                    uow, todo.workspace_id, user_id, WorkspaceRole.MEMBER
                )
            elif todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            # Capture old state for activity logging
            old_state = {
                "title": todo.title,
                "description": todo.description,
                "is_completed": todo.is_completed,
                "parent_id": str(todo.parent_id) if todo.parent_id else None,
                "position": todo.position,
            }

            # Validate new parent if changing
            if parent_id is not ... and parent_id != todo.parent_id:
                if parent_id is not None:
                    # Check parent exists and belongs to user
                    parent = await uow.todos.get(cast(UUID, parent_id))
                    if not parent:
                        raise TodoNotFoundError(str(parent_id))

                    # If workspace-scoped, parent must be in same workspace
                    if todo.workspace_id and parent.workspace_id != todo.workspace_id:
                        raise TodoNotFoundError(str(parent_id))
                    elif not todo.workspace_id and parent.user_id != user_id:
                        raise TodoNotFoundError(str(parent_id))

                    # Prevent circular reference
                    if await self._would_create_cycle(uow, todo_id, cast(UUID, parent_id)):
                        raise AppException(
                            ErrorCode.CIRCULAR_REFERENCE,
                            "Cannot move task to its own descendant",
                            400,
                        )

                todo.parent_id = cast(Optional[UUID], parent_id)

            # Update fields
            if title is not None:
                todo.title = title
            if description is not None:
                todo.description = description
            if position is not None:
                todo.position = position

            # Handle completion state
            if is_completed is not None:
                if is_completed and not todo.is_completed:
                    todo.complete()
                elif not is_completed and todo.is_completed:
                    todo.uncomplete()

            todo.updated_at = datetime.utcnow()

            updated = await uow.todos.update(todo)

            # Log activity if workspace-scoped
            if todo.workspace_id and self._activity:
                new_state = {
                    "title": updated.title,
                    "description": updated.description,
                    "is_completed": updated.is_completed,
                    "parent_id": str(updated.parent_id) if updated.parent_id else None,
                    "position": updated.position,
                }
                changes = ActivityService.compute_diff(old_state, new_state)

                if changes:
                    # Determine specific action
                    if "is_completed" in changes:
                        action = (
                            Actions.TODO_COMPLETED
                            if updated.is_completed
                            else Actions.TODO_UNCOMPLETED
                        )
                    elif "parent_id" in changes:
                        action = Actions.TODO_MOVED
                    else:
                        action = Actions.TODO_UPDATED

                    await self._activity.log(
                        uow=uow,
                        workspace_id=todo.workspace_id,
                        actor_id=user_id,
                        action=action,
                        entity_type="todo",
                        entity_id=todo_id,
                        changes=changes,
                    )

            await uow.commit()

            return updated

    async def delete(self, todo_id: UUID, user_id: UUID) -> bool:
        """Delete a todo and all its descendants (cascade).

        Requires Admin+ role in workspace context, or user ownership.
        """
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)

            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # Verify access
            if todo.workspace_id:
                await self._require_workspace_role(
                    uow, todo.workspace_id, user_id, WorkspaceRole.MEMBER
                )
            elif todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            # Log activity before delete (while todo still exists)
            if todo.workspace_id and self._activity:
                await self._activity.log(
                    uow=uow,
                    workspace_id=todo.workspace_id,
                    actor_id=user_id,
                    action=Actions.TODO_DELETED,
                    entity_type="todo",
                    entity_id=todo_id,
                    metadata={"title": todo.title},
                )

            deleted = await uow.todos.delete(todo_id)
            await uow.commit()

            return deleted  # type: ignore[no-any-return]

    async def _would_create_cycle(
        self, uow: IUnitOfWork, todo_id: UUID, new_parent_id: UUID
    ) -> bool:
        """Check if moving todo to new_parent would create a cycle."""
        current_id: Optional[UUID] = new_parent_id

        while current_id:
            if current_id == todo_id:
                return True

            current = await uow.todos.get(current_id)
            if not current:
                break

            current_id = current.parent_id

        return False

    async def _require_workspace_role(
        self,
        uow: IUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        required_role: WorkspaceRole,
    ) -> None:
        """Verify the user has at least the required role in workspace."""
        member = await uow.workspaces.get_member(workspace_id, user_id)
        if not member:
            raise NotAMemberError(str(workspace_id))
        if not has_permission(member.role, required_role):
            raise InsufficientPermissionsError(required_role.name.lower())
