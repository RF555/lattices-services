"""Pydantic schemas for Group API."""

from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GroupCreate(BaseModel):
    """Schema for creating a group."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class GroupUpdate(BaseModel):
    """Schema for updating a group."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


class GroupResponse(BaseModel):
    """Schema for Group response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str]
    created_by: UUID
    member_count: int = 0
    created_at: datetime


class GroupListResponse(BaseModel):
    """Schema for list of Groups response."""

    data: List[GroupResponse]
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

    data: List[GroupMemberResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class AddGroupMemberRequest(BaseModel):
    """Schema for adding a member to a group."""

    user_id: UUID
    role: str = Field("member", pattern="^(admin|member)$")
