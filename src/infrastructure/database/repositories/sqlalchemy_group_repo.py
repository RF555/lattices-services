"""SQLAlchemy implementation of Group repository."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.entities.group import Group, GroupMember, GroupRole
from infrastructure.database.models import GroupMemberModel, GroupModel


class SQLAlchemyGroupRepository:
    """SQLAlchemy implementation of IGroupRepository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, id: UUID) -> Group | None:
        """Get a group by ID."""
        stmt = select(GroupModel).where(GroupModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_for_workspace(self, workspace_id: UUID) -> list[Group]:
        """Get all groups in a workspace."""
        stmt = (
            select(GroupModel)
            .where(GroupModel.workspace_id == workspace_id)
            .order_by(GroupModel.created_at)
        )
        result = await self._session.execute(stmt)
        return [self._to_entity(model) for model in result.scalars()]

    async def create(self, group: Group) -> Group:
        """Create a new group."""
        model = self._to_model(group)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._to_entity(model)

    async def update(self, group: Group) -> Group:
        """Update an existing group."""
        stmt = select(GroupModel).where(GroupModel.id == group.id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError(f"Group {group.id} not found")

        model.name = group.name
        model.description = group.description

        await self._session.flush()
        return self._to_entity(model)

    async def delete(self, id: UUID) -> bool:
        """Delete a group (cascade deletes members)."""
        stmt = select(GroupModel).where(GroupModel.id == id)
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def get_member(
        self, group_id: UUID, user_id: UUID
    ) -> GroupMember | None:
        """Get a specific group member."""
        stmt = select(GroupMemberModel).where(
            GroupMemberModel.group_id == group_id,
            GroupMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._member_to_entity(model) if model else None

    async def get_members(self, group_id: UUID) -> list[GroupMember]:
        """Get all members of a group."""
        stmt = (
            select(GroupMemberModel)
            .where(GroupMemberModel.group_id == group_id)
            .order_by(GroupMemberModel.joined_at)
        )
        result = await self._session.execute(stmt)
        return [self._member_to_entity(model) for model in result.scalars()]

    async def add_member(self, member: GroupMember) -> GroupMember:
        """Add a member to a group."""
        model = self._member_to_model(member)
        self._session.add(model)
        await self._session.flush()
        await self._session.refresh(model)
        return self._member_to_entity(model)

    async def update_member_role(
        self, group_id: UUID, user_id: UUID, role: GroupRole
    ) -> GroupMember:
        """Update a group member's role."""
        stmt = select(GroupMemberModel).where(
            GroupMemberModel.group_id == group_id,
            GroupMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            raise ValueError("Group member not found")

        model.role = role.value
        await self._session.flush()
        return self._member_to_entity(model)

    async def remove_member(self, group_id: UUID, user_id: UUID) -> bool:
        """Remove a member from a group."""
        stmt = select(GroupMemberModel).where(
            GroupMemberModel.group_id == group_id,
            GroupMemberModel.user_id == user_id,
        )
        result = await self._session.execute(stmt)
        model = result.scalar_one_or_none()

        if not model:
            return False

        await self._session.delete(model)
        await self._session.flush()
        return True

    async def count_members(self, group_id: UUID) -> int:
        """Count members in a group."""
        stmt = (
            select(func.count())
            .select_from(GroupMemberModel)
            .where(GroupMemberModel.group_id == group_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    def _to_entity(self, model: GroupModel) -> Group:
        """Convert ORM model to domain entity."""
        return Group(
            id=model.id,
            workspace_id=model.workspace_id,
            name=model.name,
            description=model.description,
            created_by=model.created_by,
            created_at=model.created_at,
        )

    def _to_model(self, entity: Group) -> GroupModel:
        """Convert domain entity to ORM model."""
        return GroupModel(
            id=entity.id,
            workspace_id=entity.workspace_id,
            name=entity.name,
            description=entity.description,
            created_by=entity.created_by,
            created_at=entity.created_at,
        )

    def _member_to_entity(self, model: GroupMemberModel) -> GroupMember:
        """Convert member ORM model to domain entity."""
        return GroupMember(
            group_id=model.group_id,
            user_id=model.user_id,
            role=GroupRole(model.role),
            joined_at=model.joined_at,
        )

    def _member_to_model(self, entity: GroupMember) -> GroupMemberModel:
        """Convert member domain entity to ORM model."""
        return GroupMemberModel(
            group_id=entity.group_id,
            user_id=entity.user_id,
            role=entity.role.value,
            joined_at=entity.joined_at,
        )
