"""SQLAlchemy implementation of Workspace repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole
from infrastructure.database.models import WorkspaceMemberModel, WorkspaceModel

# Map string role values in DB to WorkspaceRole enum
_ROLE_TO_ENUM = {
    "owner": WorkspaceRole.OWNER,
    "admin": WorkspaceRole.ADMIN,
    "member": WorkspaceRole.MEMBER,
    "viewer": WorkspaceRole.VIEWER,
}

_ENUM_TO_ROLE = {v: k for k, v in _ROLE_TO_ENUM.items()}


class SQLAlchemyWorkspaceRepository:
    """SQLAlchemy implementation of IWorkspaceRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> Workspace | None:
        """Get a workspace by ID."""
        stmt = select(WorkspaceModel).where(WorkspaceModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_by_slug(self, slug: str) -> Workspace | None:
        """Get a workspace by slug."""
        stmt = select(WorkspaceModel).where(WorkspaceModel.slug == slug)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_all_for_user(self, user_id: UUID) -> list[Workspace]:
        """Get all workspaces a user is a member of."""
        stmt = (
            select(WorkspaceModel)
            .join(
                WorkspaceMemberModel,
                WorkspaceMemberModel.workspace_id == WorkspaceModel.id,
            )
            .where(WorkspaceMemberModel.user_id == user_id)
            .order_by(WorkspaceModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def create(self, workspace: Workspace) -> Workspace:
        """Create a new workspace."""
        model = self._to_model(workspace)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace."""
        stmt = select(WorkspaceModel).where(WorkspaceModel.id == workspace.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Workspace {workspace.id} not found")

        model.name = workspace.name
        model.slug = workspace.slug
        model.description = workspace.description
        model.settings = workspace.settings
        model.updated_at = workspace.updated_at

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, id: UUID) -> bool:
        """Delete a workspace (cascade deletes members)."""
        stmt = select(WorkspaceModel).where(WorkspaceModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_member(self, workspace_id: UUID, user_id: UUID) -> WorkspaceMember | None:
        """Get a workspace member by workspace and user IDs."""
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._member_to_entity(model) if model else None

    async def get_members(self, workspace_id: UUID) -> list[WorkspaceMember]:
        """Get all members of a workspace."""
        stmt = (
            select(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == workspace_id)
            .order_by(WorkspaceMemberModel.joined_at)
        )
        result = await self._session.execute(stmt)
        return [self._member_to_entity(model) for model in result.scalars()]

    async def add_member(self, member: WorkspaceMember) -> WorkspaceMember:
        """Add a member to a workspace."""
        model = self._member_to_model(member)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._member_to_entity(model)

    async def update_member_role(
        self, workspace_id: UUID, user_id: UUID, role: WorkspaceRole
    ) -> WorkspaceMember:
        """Update a member's role in a workspace."""
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError("Member not found in workspace")

        model.role = _ENUM_TO_ROLE[role]
        await self._session.flush()
        return self._member_to_entity(model)

    async def remove_member(self, workspace_id: UUID, user_id: UUID) -> bool:
        """Remove a member from a workspace."""
        stmt = select(WorkspaceMemberModel).where(
            WorkspaceMemberModel.workspace_id == workspace_id,
            WorkspaceMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def count_members(self, workspace_id: UUID) -> int:
        """Count the number of members in a workspace."""
        stmt = (
            select(func.count())
            .select_from(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.workspace_id == workspace_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_owners(self, workspace_id: UUID) -> int:
        """Count the number of owners in a workspace."""
        stmt = (
            select(func.count())
            .select_from(WorkspaceMemberModel)
            .where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.role == "owner",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_user_workspaces(self, user_id: UUID) -> int:
        """Count the number of workspaces a user is a member of."""
        stmt = (
            select(func.count())
            .select_from(WorkspaceMemberModel)
            .where(WorkspaceMemberModel.user_id == user_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    def _to_entity(self, model: WorkspaceModel) -> Workspace:
        """Convert ORM model to domain entity."""
        return Workspace(
            id=model.id,
            name=model.name,
            slug=model.slug,
            description=model.description,
            created_by=model.created_by,
            settings=model.settings or {},
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    def _to_model(self, entity: Workspace) -> WorkspaceModel:
        """Convert domain entity to ORM model."""
        return WorkspaceModel(
            id=entity.id,
            name=entity.name,
            slug=entity.slug,
            description=entity.description,
            created_by=entity.created_by,
            settings=entity.settings,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def _member_to_entity(self, model: WorkspaceMemberModel) -> WorkspaceMember:
        """Convert member ORM model to domain entity."""
        return WorkspaceMember(
            workspace_id=model.workspace_id,
            user_id=model.user_id,
            role=_ROLE_TO_ENUM[model.role],
            joined_at=model.joined_at,
            invited_by=model.invited_by,
        )

    def _member_to_model(self, entity: WorkspaceMember) -> WorkspaceMemberModel:
        """Convert member domain entity to ORM model."""
        return WorkspaceMemberModel(
            workspace_id=entity.workspace_id,
            user_id=entity.user_id,
            role=_ENUM_TO_ROLE[entity.role],
            joined_at=entity.joined_at,
            invited_by=entity.invited_by,
        )
