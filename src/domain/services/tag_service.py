"""Tag service layer with business logic."""

from typing import Callable, Dict, List, Optional
from uuid import UUID

from core.exceptions import (
    AppException,
    ErrorCode,
    InsufficientPermissionsError,
    NotAMemberError,
    TagNotFoundError,
    TodoNotFoundError,
)
from domain.entities.tag import Tag, TagWithCount
from domain.entities.workspace import WorkspaceRole, has_permission
from domain.repositories.unit_of_work import IUnitOfWork


class TagService:
    """Service layer for Tag business logic."""

    def __init__(self, uow_factory: Callable[[], IUnitOfWork]) -> None:
        self._uow_factory = uow_factory

    async def get_all_for_user(
        self, user_id: UUID, workspace_id: Optional[UUID] = None
    ) -> List[TagWithCount]:
        """Get all tags for user with usage counts, optionally scoped to workspace."""
        async with self._uow_factory() as uow:
            if workspace_id:
                await self._require_workspace_role(
                    uow, workspace_id, user_id, WorkspaceRole.VIEWER
                )
                tags = await uow.tags.get_all_for_workspace(workspace_id)
            else:
                tags = await uow.tags.get_all_for_user(user_id)

            tag_ids = [tag.id for tag in tags]
            usage_counts = await uow.tags.get_usage_counts_batch(tag_ids)
            return [
                TagWithCount(tag=tag, usage_count=usage_counts.get(tag.id, 0))
                for tag in tags
            ]

    async def get_by_id(self, tag_id: UUID, user_id: UUID) -> Tag:
        """Get a specific tag, verifying workspace membership or user ownership."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag:
                raise TagNotFoundError(str(tag_id))

            # Check access via workspace membership or direct ownership
            if tag.workspace_id:
                member = await uow.workspaces.get_member(tag.workspace_id, user_id)
                if not member:
                    raise TagNotFoundError(str(tag_id))
            elif tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            return tag

    async def create(
        self,
        user_id: UUID,
        name: str,
        color_hex: str = "#3B82F6",
        workspace_id: Optional[UUID] = None,
    ) -> Tag:
        """Create a new tag. Requires Member+ role if workspace_id is provided."""
        async with self._uow_factory() as uow:
            if workspace_id:
                await self._require_workspace_role(
                    uow, workspace_id, user_id, WorkspaceRole.MEMBER
                )
                # Check for duplicate name within workspace
                existing = await uow.tags.get_by_name_in_workspace(workspace_id, name)
            else:
                # Check for duplicate name for user
                existing = await uow.tags.get_by_name(user_id, name)

            if existing:
                raise AppException(
                    ErrorCode.DUPLICATE_TAG,
                    f"Tag '{name}' already exists",
                    409,
                    {"name": name},
                )

            tag = Tag(
                user_id=user_id,
                workspace_id=workspace_id,
                name=name,
                color_hex=color_hex,
            )

            created = await uow.tags.create(tag)
            await uow.commit()
            return created

    async def update(
        self,
        tag_id: UUID,
        user_id: UUID,
        name: Optional[str] = None,
        color_hex: Optional[str] = None,
    ) -> Tag:
        """Update an existing tag."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag:
                raise TagNotFoundError(str(tag_id))

            # Verify access via workspace membership or user ownership
            if tag.workspace_id:
                await self._require_workspace_role(
                    uow, tag.workspace_id, user_id, WorkspaceRole.MEMBER
                )
            elif tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            if name and name != tag.name:
                # Check for duplicate name
                if tag.workspace_id:
                    existing = await uow.tags.get_by_name_in_workspace(
                        tag.workspace_id, name
                    )
                else:
                    existing = await uow.tags.get_by_name(user_id, name)
                if existing:
                    raise AppException(
                        ErrorCode.DUPLICATE_TAG,
                        f"Tag '{name}' already exists",
                        409,
                        {"name": name},
                    )
                tag.name = name

            if color_hex:
                tag.color_hex = color_hex

            updated = await uow.tags.update(tag)
            await uow.commit()
            return updated

    async def delete(self, tag_id: UUID, user_id: UUID) -> bool:
        """Delete a tag (detaches from all todos via cascade)."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag:
                raise TagNotFoundError(str(tag_id))

            # Verify access
            if tag.workspace_id:
                await self._require_workspace_role(
                    uow, tag.workspace_id, user_id, WorkspaceRole.MEMBER
                )
            elif tag.user_id != user_id:
                raise TagNotFoundError(str(tag_id))

            deleted = await uow.tags.delete(tag_id)
            await uow.commit()
            return deleted  # type: ignore[no-any-return]

    async def attach_to_todo(
        self,
        tag_id: UUID,
        todo_id: UUID,
        user_id: UUID,
    ) -> None:
        """Attach a tag to a todo. Verifies workspace membership or user ownership."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag:
                raise TagNotFoundError(str(tag_id))

            todo = await uow.todos.get(todo_id)
            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # Verify access - tag and todo must be in same workspace (or both owned by user)
            if tag.workspace_id:
                await self._require_workspace_role(
                    uow, tag.workspace_id, user_id, WorkspaceRole.MEMBER
                )
                if todo.workspace_id != tag.workspace_id:
                    raise TodoNotFoundError(str(todo_id))
            else:
                if tag.user_id != user_id:
                    raise TagNotFoundError(str(tag_id))
                if todo.user_id != user_id:
                    raise TodoNotFoundError(str(todo_id))

            await uow.tags.attach_to_todo(tag_id, todo_id)
            await uow.commit()

    async def detach_from_todo(
        self,
        tag_id: UUID,
        todo_id: UUID,
        user_id: UUID,
    ) -> None:
        """Detach a tag from a todo."""
        async with self._uow_factory() as uow:
            tag = await uow.tags.get(tag_id)
            if not tag:
                raise TagNotFoundError(str(tag_id))

            todo = await uow.todos.get(todo_id)
            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # Verify access
            if tag.workspace_id:
                await self._require_workspace_role(
                    uow, tag.workspace_id, user_id, WorkspaceRole.MEMBER
                )
            else:
                if tag.user_id != user_id:
                    raise TagNotFoundError(str(tag_id))
                if todo.user_id != user_id:
                    raise TodoNotFoundError(str(todo_id))

            await uow.tags.detach_from_todo(tag_id, todo_id)
            await uow.commit()

    async def get_tags_for_todo(self, todo_id: UUID, user_id: UUID) -> List[Tag]:
        """Get all tags attached to a todo."""
        async with self._uow_factory() as uow:
            todo = await uow.todos.get(todo_id)
            if not todo:
                raise TodoNotFoundError(str(todo_id))

            # Verify access
            if todo.workspace_id:
                member = await uow.workspaces.get_member(todo.workspace_id, user_id)
                if not member:
                    raise TodoNotFoundError(str(todo_id))
            elif todo.user_id != user_id:
                raise TodoNotFoundError(str(todo_id))

            return await uow.tags.get_for_todo(todo_id)  # type: ignore[no-any-return]

    async def get_tags_for_todos_batch(
        self, todo_ids: List[UUID]
    ) -> Dict[UUID, List[Tag]]:
        """Get tags for multiple todos in a single query (batch fetch)."""
        if not todo_ids:
            return {}
        async with self._uow_factory() as uow:
            return await uow.tags.get_for_todos_batch(todo_ids)  # type: ignore[no-any-return]

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
