"""Pydantic schemas for Workspace API."""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    """Schema for creating a Workspace."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class WorkspaceUpdate(BaseModel):
    """Schema for updating a Workspace (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)


class WorkspaceResponse(BaseModel):
    """Schema for Workspace response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "My Team",
                "slug": "my-team",
                "description": "Team workspace for project management",
                "created_by": "456e4567-e89b-12d3-a456-426614174000",
                "member_count": 3,
                "created_at": "2026-02-01T10:00:00",
                "updated_at": "2026-02-01T10:00:00",
            }
        },
    )

    id: UUID
    name: str
    slug: str
    description: Optional[str]
    created_by: UUID
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class WorkspaceMemberResponse(BaseModel):
    """Schema for Workspace Member response."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    email: str = ""
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    joined_at: datetime


class WorkspaceListResponse(BaseModel):
    """Schema for list of Workspaces response."""

    data: List[WorkspaceResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class WorkspaceDetailResponse(BaseModel):
    """Schema for single Workspace response."""

    data: WorkspaceResponse


class WorkspaceMemberListResponse(BaseModel):
    """Schema for list of Workspace Members response."""

    data: List[WorkspaceMemberResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class AddMemberRequest(BaseModel):
    """Schema for adding a member to a workspace."""

    user_id: UUID
    role: str = Field("member", pattern="^(admin|member|viewer)$")


class UpdateMemberRoleRequest(BaseModel):
    """Schema for updating a member's role."""

    role: str = Field(..., pattern="^(admin|member|viewer)$")


class TransferOwnershipRequest(BaseModel):
    """Schema for transferring workspace ownership."""

    new_owner_id: UUID
