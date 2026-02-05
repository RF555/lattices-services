"""Pydantic schemas for Invitation API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateInvitationRequest(BaseModel):
    """Schema for creating a workspace invitation."""

    email: str = Field(..., min_length=3, max_length=255)
    role: str = Field("member", pattern="^(admin|member|viewer)$")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Basic email validation."""
        v = v.strip().lower()
        if "@" not in v or "." not in v.split("@")[-1]:
            raise ValueError("Invalid email address")
        return v


class AcceptInvitationRequest(BaseModel):
    """Schema for accepting a workspace invitation."""

    token: str = Field(..., min_length=1)


class InvitationResponse(BaseModel):
    """Schema for Invitation response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "workspace_id": "456e4567-e89b-12d3-a456-426614174000",
                "workspace_name": "My Team",
                "email": "user@example.com",
                "role": "member",
                "status": "pending",
                "invited_by": "789e4567-e89b-12d3-a456-426614174000",
                "created_at": "2026-02-01T10:00:00",
                "expires_at": "2026-02-08T10:00:00",
            }
        },
    )

    id: UUID
    workspace_id: UUID
    workspace_name: str = ""
    email: str
    role: str
    status: str
    invited_by: UUID
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None = None


class InvitationListResponse(BaseModel):
    """Schema for list of Invitations response."""

    data: list[InvitationResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class InvitationCreatedResponse(BaseModel):
    """Schema for invitation creation response (includes raw token)."""

    data: InvitationResponse
    token: str = Field(
        ...,
        description="Raw invitation token. Share this with the invitee. "
        "This value is only shown once.",
    )


class AcceptInvitationResponse(BaseModel):
    """Schema for accepting an invitation response."""

    workspace_id: UUID
    workspace_name: str
    role: str
    message: str = "Invitation accepted successfully"
