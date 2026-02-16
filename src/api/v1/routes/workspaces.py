"""Workspace API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from api.dependencies.auth import CurrentUser, InitializedUser
from api.v1.dependencies import get_workspace_service
from api.v1.schemas.workspace import (
    AddMemberRequest,
    TransferOwnershipRequest,
    UpdateMemberRoleRequest,
    WorkspaceCreate,
    WorkspaceDetailResponse,
    WorkspaceListResponse,
    WorkspaceMemberListResponse,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)
from core.rate_limit import limiter
from domain.entities.workspace import WorkspaceMember, WorkspaceRole
from domain.services.workspace_service import WorkspaceService

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# Map string role values to WorkspaceRole enum
_ROLE_MAP = {
    "owner": WorkspaceRole.OWNER,
    "admin": WorkspaceRole.ADMIN,
    "member": WorkspaceRole.MEMBER,
    "viewer": WorkspaceRole.VIEWER,
}

_ROLE_TO_STR = {v: k for k, v in _ROLE_MAP.items()}


@router.get(
    "",
    response_model=WorkspaceListResponse,
    summary="List user's workspaces",
    responses={200: {"description": "List of workspaces the user belongs to"}},
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_workspaces(
    request: Request,
    user: InitializedUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceListResponse:
    """Get all workspaces the authenticated user is a member of."""
    workspaces = await service.get_all_for_user(user.id)
    data = [
        WorkspaceResponse(
            id=ws.id,
            name=ws.name,
            slug=ws.slug,
            description=ws.description,
            created_by=ws.created_by,
            created_at=ws.created_at,
            updated_at=ws.updated_at,
        )
        for ws in workspaces
    ]
    return WorkspaceListResponse(data=data, meta={"total": len(data)})


@router.post(
    "",
    response_model=WorkspaceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
    responses={
        201: {"description": "Workspace created successfully"},
        409: {"description": "Workspace slug already taken"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def create_workspace(
    request: Request,
    body: WorkspaceCreate,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetailResponse:
    """Create a new workspace. The creator is automatically added as Owner."""
    workspace = await service.create(
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    return WorkspaceDetailResponse(
        data=WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            description=workspace.description,
            created_by=workspace.created_by,
            member_count=1,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Get workspace details",
    responses={
        200: {"description": "Workspace details"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_workspace(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetailResponse:
    """Get a specific workspace by ID. Requires membership."""
    workspace = await service.get_by_id(workspace_id, user.id)
    return WorkspaceDetailResponse(
        data=WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            description=workspace.description,
            created_by=workspace.created_by,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )
    )


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceDetailResponse,
    summary="Update workspace",
    responses={
        200: {"description": "Workspace updated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_workspace(
    request: Request,
    workspace_id: UUID,
    body: WorkspaceUpdate,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceDetailResponse:
    """Update a workspace. Requires Admin+ role."""
    workspace = await service.update(
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    return WorkspaceDetailResponse(
        data=WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            description=workspace.description,
            created_by=workspace.created_by,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )
    )


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete workspace",
    responses={
        204: {"description": "Workspace deleted"},
        403: {"description": "Insufficient permissions (Owner only)"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def delete_workspace(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    """Delete a workspace and all its data. Requires Owner role."""
    await service.delete(workspace_id, user.id)
    return None


# --- Member Management ---


@router.get(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberListResponse,
    summary="List workspace members",
    responses={
        200: {"description": "List of workspace members"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_members(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberListResponse:
    """Get all members of a workspace. Requires membership."""
    members = await service.get_members(workspace_id, user.id)
    data = [_build_member_response(m) for m in members]
    return WorkspaceMemberListResponse(data=data, meta={"total": len(data)})


@router.post(
    "/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add workspace member",
    responses={
        201: {"description": "Member added"},
        403: {"description": "Insufficient permissions (Admin+ only)"},
        404: {"description": "Workspace not found"},
        409: {"description": "User is already a member"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def add_member(
    request: Request,
    workspace_id: UUID,
    body: AddMemberRequest,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberResponse:
    """Add a member to a workspace. Requires Admin+ role."""
    role = _ROLE_MAP.get(body.role, WorkspaceRole.MEMBER)
    member = await service.add_member(
        workspace_id=workspace_id,
        user_id=user.id,
        target_user_id=body.user_id,
        role=role,
    )
    return _build_member_response(member)


@router.patch(
    "/{workspace_id}/members/{member_user_id}",
    response_model=WorkspaceMemberResponse,
    summary="Update member role",
    responses={
        200: {"description": "Role updated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Workspace or member not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def update_member_role(
    request: Request,
    workspace_id: UUID,
    member_user_id: UUID,
    body: UpdateMemberRoleRequest,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> WorkspaceMemberResponse:
    """Update a member's role. Requires Admin+ role."""
    role = _ROLE_MAP.get(body.role, WorkspaceRole.MEMBER)
    member = await service.update_member_role(
        workspace_id=workspace_id,
        user_id=user.id,
        target_user_id=member_user_id,
        role=role,
    )
    return _build_member_response(member)


@router.delete(
    "/{workspace_id}/members/{member_user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove workspace member",
    responses={
        204: {"description": "Member removed"},
        400: {"description": "Cannot remove last owner"},
        403: {"description": "Insufficient permissions"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def remove_member(
    request: Request,
    workspace_id: UUID,
    member_user_id: UUID,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    """Remove a member from a workspace or leave the workspace."""
    await service.remove_member(
        workspace_id=workspace_id,
        user_id=user.id,
        target_user_id=member_user_id,
    )
    return None


@router.post(
    "/{workspace_id}/transfer-ownership",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Transfer workspace ownership",
    responses={
        204: {"description": "Ownership transferred"},
        403: {"description": "Must be workspace owner"},
        404: {"description": "Workspace not found or target not a member"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def transfer_ownership(
    request: Request,
    workspace_id: UUID,
    body: TransferOwnershipRequest,
    user: CurrentUser,
    service: WorkspaceService = Depends(get_workspace_service),
) -> None:
    """Transfer workspace ownership to another member. Requires Owner role."""
    await service.transfer_ownership(
        workspace_id=workspace_id,
        current_owner_id=user.id,
        new_owner_id=body.new_owner_id,
    )
    return None


def _build_member_response(member: WorkspaceMember) -> WorkspaceMemberResponse:
    """Convert domain entity to response schema."""
    return WorkspaceMemberResponse(
        user_id=member.user_id,
        role=_ROLE_TO_STR.get(member.role, "member"),
        joined_at=member.joined_at,
    )
