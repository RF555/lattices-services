"""Group API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_group_service
from api.v1.schemas.group import (
    AddGroupMemberRequest,
    GroupCreate,
    GroupDetailResponse,
    GroupListResponse,
    GroupMemberListResponse,
    GroupMemberResponse,
    GroupResponse,
    GroupUpdate,
)
from core.rate_limit import limiter
from domain.entities.group import GroupMember, GroupRole
from domain.services.group_service import GroupService

router = APIRouter(
    prefix="/workspaces/{workspace_id}/groups",
    tags=["groups"],
)

_ROLE_MAP = {
    "admin": GroupRole.ADMIN,
    "member": GroupRole.MEMBER,
}


@router.get(
    "",
    response_model=GroupListResponse,
    summary="List workspace groups",
    responses={
        200: {"description": "List of groups in the workspace"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_groups(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> GroupListResponse:
    """Get all groups in a workspace. Requires membership."""
    groups = await service.get_for_workspace(workspace_id, user.id)
    data = [
        GroupResponse(
            id=g.id,
            workspace_id=g.workspace_id,
            name=g.name,
            description=g.description,
            created_by=g.created_by,
            created_at=g.created_at,
        )
        for g in groups
    ]
    return GroupListResponse(data=data, meta={"total": len(data)})


@router.post(
    "",
    response_model=GroupDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a group",
    responses={
        201: {"description": "Group created"},
        403: {"description": "Insufficient permissions (Admin+ only)"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def create_group(
    request: Request,
    workspace_id: UUID,
    body: GroupCreate,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> GroupDetailResponse:
    """Create a new group in a workspace. Requires Admin+ role."""
    group = await service.create(
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    return GroupDetailResponse(
        data=GroupResponse(
            id=group.id,
            workspace_id=group.workspace_id,
            name=group.name,
            description=group.description,
            created_by=group.created_by,
            member_count=1,
            created_at=group.created_at,
        )
    )


@router.patch(
    "/{group_id}",
    response_model=GroupDetailResponse,
    summary="Update a group",
    responses={
        200: {"description": "Group updated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Group not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_group(
    request: Request,
    workspace_id: UUID,
    group_id: UUID,
    body: GroupUpdate,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> GroupDetailResponse:
    """Update a group. Requires workspace Admin+ or group Admin."""
    group = await service.update(
        workspace_id=workspace_id,
        group_id=group_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    return GroupDetailResponse(
        data=GroupResponse(
            id=group.id,
            workspace_id=group.workspace_id,
            name=group.name,
            description=group.description,
            created_by=group.created_by,
            created_at=group.created_at,
        )
    )


@router.delete(
    "/{group_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a group",
    responses={
        204: {"description": "Group deleted"},
        403: {"description": "Insufficient permissions (Admin+ only)"},
        404: {"description": "Group not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def delete_group(
    request: Request,
    workspace_id: UUID,
    group_id: UUID,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> None:
    """Delete a group. Requires workspace Admin+ role."""
    await service.delete(workspace_id, group_id, user.id)
    return None


# --- Group Member Management ---


@router.get(
    "/{group_id}/members",
    response_model=GroupMemberListResponse,
    summary="List group members",
    responses={
        200: {"description": "List of group members"},
        403: {"description": "Not a workspace member"},
        404: {"description": "Group not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_group_members(
    request: Request,
    workspace_id: UUID,
    group_id: UUID,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> GroupMemberListResponse:
    """Get all members of a group. Requires workspace membership."""
    members = await service.get_members(workspace_id, group_id, user.id)
    data = [_build_member_response(m) for m in members]
    return GroupMemberListResponse(data=data, meta={"total": len(data)})


@router.post(
    "/{group_id}/members",
    response_model=GroupMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add group member",
    responses={
        201: {"description": "Member added to group"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Group not found"},
        409: {"description": "Already a group member"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def add_group_member(
    request: Request,
    workspace_id: UUID,
    group_id: UUID,
    body: AddGroupMemberRequest,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> GroupMemberResponse:
    """Add a member to a group. Requires workspace Admin+ or group Admin."""
    role = _ROLE_MAP.get(body.role, GroupRole.MEMBER)
    member = await service.add_member(
        workspace_id=workspace_id,
        group_id=group_id,
        user_id=user.id,
        target_user_id=body.user_id,
        role=role,
    )
    return _build_member_response(member)


@router.delete(
    "/{group_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove group member",
    responses={
        204: {"description": "Member removed from group"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Group or member not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def remove_group_member(
    request: Request,
    workspace_id: UUID,
    group_id: UUID,
    member_user_id: UUID,
    user: CurrentUser,
    service: GroupService = Depends(get_group_service),
) -> None:
    """Remove a member from a group or leave the group."""
    await service.remove_member(
        workspace_id=workspace_id,
        group_id=group_id,
        user_id=user.id,
        target_user_id=member_user_id,
    )
    return None


def _build_member_response(member: GroupMember) -> GroupMemberResponse:
    """Convert domain entity to response schema."""
    return GroupMemberResponse(
        user_id=member.user_id,
        role=member.role.value,
        joined_at=member.joined_at,
    )
