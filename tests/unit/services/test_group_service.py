"""Unit tests for GroupService."""

from uuid import UUID, uuid4

import pytest

from core.exceptions import (
    AlreadyAGroupMemberError,
    GroupMemberNotFoundError,
    GroupNotFoundError,
    InsufficientPermissionsError,
    NotAMemberError,
    WorkspaceNotFoundError,
)
from domain.entities.group import Group, GroupMember, GroupRole
from domain.entities.workspace import Workspace, WorkspaceMember, WorkspaceRole
from domain.services.group_service import GroupService
from tests.unit.conftest import FakeUnitOfWork


@pytest.fixture
def service(uow: FakeUnitOfWork) -> GroupService:
    return GroupService(lambda: uow)


@pytest.fixture
def workspace(workspace_id: UUID, user_id: UUID) -> Workspace:
    return Workspace(id=workspace_id, name="Test WS", slug="test-ws", created_by=user_id)


@pytest.fixture
def group(workspace_id: UUID, user_id: UUID) -> Group:
    return Group(workspace_id=workspace_id, name="Dev Team", created_by=user_id)


# --- get_for_workspace ---


class TestGetForWorkspace:
    @pytest.mark.asyncio
    async def test_returns_groups(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        g1 = Group(workspace_id=workspace_id, name="G1", created_by=user_id)
        g2 = Group(workspace_id=workspace_id, name="G2", created_by=user_id)
        uow.groups.get_for_workspace.return_value = [g1, g2]

        result = await service.get_for_workspace(workspace_id, user_id)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_raises_workspace_not_found(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = None

        with pytest.raises(WorkspaceNotFoundError):
            await service.get_for_workspace(workspace_id, user_id)

    @pytest.mark.asyncio
    async def test_raises_not_a_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = None

        with pytest.raises(NotAMemberError):
            await service.get_for_workspace(workspace_id, user_id)


# --- get_by_id ---


class TestGetById:
    @pytest.mark.asyncio
    async def test_returns_group(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.groups.get.return_value = group

        result = await service.get_by_id(workspace_id, group.id, user_id)
        assert result.name == "Dev Team"

    @pytest.mark.asyncio
    async def test_raises_group_not_found(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.groups.get.return_value = None

        with pytest.raises(GroupNotFoundError):
            await service.get_by_id(workspace_id, uuid4(), user_id)

    @pytest.mark.asyncio
    async def test_raises_group_not_found_wrong_workspace(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        wrong_ws = uuid4()
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.VIEWER
        )
        uow.groups.get.return_value = Group(workspace_id=wrong_ws, name="Other", created_by=user_id)

        with pytest.raises(GroupNotFoundError):
            await service.get_by_id(workspace_id, uuid4(), user_id)


# --- create ---


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_group_with_admin_membership(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        created_group = Group(workspace_id=workspace_id, name="New Group", created_by=user_id)
        uow.groups.create.return_value = created_group

        result = await service.create(workspace_id, user_id, "New Group")

        assert result.name == "New Group"
        uow.groups.add_member.assert_called_once()
        add_call = uow.groups.add_member.call_args[0][0]
        assert add_call.role == GroupRole.ADMIN
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_insufficient_permissions_for_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace: Workspace,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.workspaces.get.return_value = workspace
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.create(workspace_id, user_id, "New Group")


# --- update ---


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_by_workspace_admin(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        updated_group = Group(
            id=group.id, workspace_id=workspace_id, name="Updated", created_by=user_id
        )
        uow.groups.update.return_value = updated_group

        result = await service.update(workspace_id, group.id, user_id, name="Updated")

        assert result.name == "Updated"
        assert uow.committed

    @pytest.mark.asyncio
    async def test_updates_by_group_admin(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        # workspace member but not admin
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        # but is group admin
        uow.groups.get_member.return_value = GroupMember(
            group_id=group.id, user_id=user_id, role=GroupRole.ADMIN
        )
        uow.groups.update.return_value = group

        result = await service.update(workspace_id, group.id, user_id, name="Updated")
        assert result is not None
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_for_regular_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.MEMBER
        )
        uow.groups.get_member.return_value = GroupMember(
            group_id=group.id, user_id=user_id, role=GroupRole.MEMBER
        )

        with pytest.raises(InsufficientPermissionsError):
            await service.update(workspace_id, group.id, user_id, name="Nope")


# --- delete ---


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes_group(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        uow.groups.delete.return_value = True

        result = await service.delete(workspace_id, group.id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_group_not_found(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
    ):
        uow.groups.get.return_value = None

        with pytest.raises(GroupNotFoundError):
            await service.delete(workspace_id, uuid4(), user_id)


# --- add_member ---


class TestAddMember:
    @pytest.mark.asyncio
    async def test_adds_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        target = uuid4()
        uow.groups.get.return_value = group
        uow.workspaces.get_member.side_effect = [
            # actor is ws admin
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            # target is ws member
            WorkspaceMember(workspace_id=workspace_id, user_id=target, role=WorkspaceRole.MEMBER),
        ]
        uow.groups.get_member.return_value = None  # not yet in group
        new_member = GroupMember(group_id=group.id, user_id=target, role=GroupRole.MEMBER)
        uow.groups.add_member.return_value = new_member

        result = await service.add_member(workspace_id, group.id, user_id, target)

        assert result.user_id == target
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_not_ws_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        target = uuid4()
        uow.groups.get.return_value = group
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            None,  # target not in workspace
        ]

        with pytest.raises(NotAMemberError):
            await service.add_member(workspace_id, group.id, user_id, target)

    @pytest.mark.asyncio
    async def test_raises_already_group_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        target = uuid4()
        uow.groups.get.return_value = group
        uow.workspaces.get_member.side_effect = [
            WorkspaceMember(workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN),
            WorkspaceMember(workspace_id=workspace_id, user_id=target, role=WorkspaceRole.MEMBER),
        ]
        uow.groups.get_member.return_value = GroupMember(
            group_id=group.id, user_id=target, role=GroupRole.MEMBER
        )

        with pytest.raises(AlreadyAGroupMemberError):
            await service.add_member(workspace_id, group.id, user_id, target)


# --- remove_member ---


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_member(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        target = uuid4()
        uow.groups.get.return_value = group
        uow.groups.get_member.side_effect = [
            GroupMember(group_id=group.id, user_id=target, role=GroupRole.MEMBER),
        ]
        uow.workspaces.get_member.return_value = WorkspaceMember(
            workspace_id=workspace_id, user_id=user_id, role=WorkspaceRole.ADMIN
        )
        uow.groups.remove_member.return_value = True

        result = await service.remove_member(workspace_id, group.id, user_id, target)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_self_removal(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        uow.groups.get_member.return_value = GroupMember(
            group_id=group.id, user_id=user_id, role=GroupRole.MEMBER
        )
        uow.groups.remove_member.return_value = True

        result = await service.remove_member(workspace_id, group.id, user_id, user_id)

        assert result is True
        assert uow.committed

    @pytest.mark.asyncio
    async def test_raises_member_not_found(
        self,
        service: GroupService,
        uow: FakeUnitOfWork,
        workspace_id: UUID,
        user_id: UUID,
        group: Group,
    ):
        uow.groups.get.return_value = group
        uow.groups.get_member.return_value = None

        with pytest.raises(GroupMemberNotFoundError):
            await service.remove_member(workspace_id, group.id, user_id, uuid4())
