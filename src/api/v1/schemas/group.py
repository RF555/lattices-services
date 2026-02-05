"""Pydantic schemas for Group API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    """Schema for creating a group."""

    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class GroupUpdate(BaseModel):
    """Schema for updating a group."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class GroupResponse(BaseModel):
    """Schema for Group response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    created_by: UUID
    member_count: int = 0
    created_at: datetime


class GroupListResponse(BaseModel):
    """Schema for list of Groups response."""

    data: list[GroupResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class GroupDetailResponse(BaseModel):
    """Schema for single Group response."""

    data: GroupResponse


class GroupMemberResponse(BaseModel):
    """Schema for Group Member response."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    role: str
    joined_at: datetime


class GroupMemberListResponse(BaseModel):
    """Schema for list of Group Members response."""

    data: list[GroupMemberResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class AddGroupMemberRequest(BaseModel):
    """Schema for adding a member to a group."""

    user_id: UUID
    role: str = Field("member", pattern="^(admin|member)$")
