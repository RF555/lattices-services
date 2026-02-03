"""Invitation API routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from api.dependencies.auth import CurrentUser
from api.v1.dependencies import get_invitation_service
from api.v1.schemas.invitation import (
    AcceptInvitationRequest,
    AcceptInvitationResponse,
    CreateInvitationRequest,
    InvitationCreatedResponse,
    InvitationListResponse,
    InvitationResponse,
)
from core.rate_limit import limiter
from domain.services.invitation_service import InvitationService

# Workspace-scoped invitation routes
workspace_invitations_router = APIRouter(
    prefix="/workspaces/{workspace_id}/invitations",
    tags=["invitations"],
)

# User-scoped invitation routes (accept, pending)
invitations_router = APIRouter(
    prefix="/invitations",
    tags=["invitations"],
)


@workspace_invitations_router.post(
    "",
    response_model=InvitationCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create workspace invitation",
    responses={
        201: {"description": "Invitation created"},
        403: {"description": "Insufficient permissions (Admin+ only)"},
        404: {"description": "Workspace not found"},
        409: {"description": "Duplicate invitation or already a member"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def create_invitation(
    request: Request,
    workspace_id: UUID,
    body: CreateInvitationRequest,
    user: CurrentUser,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationCreatedResponse:
    """Create an invitation to join a workspace. Requires Admin+ role."""
    invitation, raw_token = await service.create_invitation(
        workspace_id=workspace_id,
        user_id=user.id,
        email=body.email,
        role=body.role,
    )
    return InvitationCreatedResponse(
        data=InvitationResponse(
            id=invitation.id,
            workspace_id=invitation.workspace_id,
            email=invitation.email,
            role=invitation.role,
            status=invitation.status.value,
            invited_by=invitation.invited_by,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            accepted_at=invitation.accepted_at,
        ),
        token=raw_token,
    )


@workspace_invitations_router.get(
    "",
    response_model=InvitationListResponse,
    summary="List workspace invitations",
    responses={
        200: {"description": "List of workspace invitations"},
        403: {"description": "Not a member"},
        404: {"description": "Workspace not found"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def list_workspace_invitations(
    request: Request,
    workspace_id: UUID,
    user: CurrentUser,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationListResponse:
    """List all invitations for a workspace. Requires membership."""
    invitations = await service.get_workspace_invitations(workspace_id, user.id)
    data = [
        InvitationResponse(
            id=inv.id,
            workspace_id=inv.workspace_id,
            email=inv.email,
            role=inv.role,
            status=inv.status.value,
            invited_by=inv.invited_by,
            created_at=inv.created_at,
            expires_at=inv.expires_at,
            accepted_at=inv.accepted_at,
        )
        for inv in invitations
    ]
    return InvitationListResponse(data=data, meta={"total": len(data)})


@workspace_invitations_router.delete(
    "/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke invitation",
    responses={
        204: {"description": "Invitation revoked"},
        403: {"description": "Insufficient permissions (Admin+ only)"},
        404: {"description": "Invitation not found"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def revoke_invitation(
    request: Request,
    workspace_id: UUID,
    invitation_id: UUID,
    user: CurrentUser,
    service: InvitationService = Depends(get_invitation_service),
) -> None:
    """Revoke a pending invitation. Requires Admin+ role."""
    await service.revoke_invitation(
        workspace_id=workspace_id,
        invitation_id=invitation_id,
        user_id=user.id,
    )
    return None


# --- User-scoped routes ---


@invitations_router.post(
    "/accept",
    response_model=AcceptInvitationResponse,
    summary="Accept invitation",
    responses={
        200: {"description": "Invitation accepted, user added to workspace"},
        400: {"description": "Invitation expired or invalid"},
        403: {"description": "Email mismatch"},
        404: {"description": "Invitation not found"},
        409: {"description": "Already a member"},
    },
)
@limiter.limit("10/minute")  # type: ignore[untyped-decorator]
async def accept_invitation(
    request: Request,
    body: AcceptInvitationRequest,
    user: CurrentUser,
    service: InvitationService = Depends(get_invitation_service),
) -> AcceptInvitationResponse:
    """Accept a workspace invitation using the invitation token."""
    member = await service.accept_invitation(
        token=body.token,
        user_id=user.id,
        user_email=user.email,
    )

    role_str = member.role.name.lower()

    return AcceptInvitationResponse(
        workspace_id=member.workspace_id,
        workspace_name="",  # Would need workspace lookup for name
        role=role_str,
    )


@invitations_router.get(
    "/pending",
    response_model=InvitationListResponse,
    summary="Get pending invitations",
    responses={
        200: {"description": "List of pending invitations for the current user"},
    },
)
@limiter.limit("30/minute")  # type: ignore[untyped-decorator]
async def get_pending_invitations(
    request: Request,
    user: CurrentUser,
    service: InvitationService = Depends(get_invitation_service),
) -> InvitationListResponse:
    """Get all pending invitations for the current user's email."""
    invitations = await service.get_user_pending_invitations(user.email)
    data = [
        InvitationResponse(
            id=inv.id,
            workspace_id=inv.workspace_id,
            email=inv.email,
            role=inv.role,
            status=inv.status.value,
            invited_by=inv.invited_by,
            created_at=inv.created_at,
            expires_at=inv.expires_at,
            accepted_at=inv.accepted_at,
        )
        for inv in invitations
    ]
    return InvitationListResponse(data=data, meta={"total": len(data)})
