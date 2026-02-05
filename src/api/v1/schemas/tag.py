"""Pydantic schemas for Tag API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagBase(BaseModel):
    """Base schema for Tag."""

    name: str = Field(..., min_length=1, max_length=50)
    color_hex: str = Field("#3B82F6", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("color_hex")
    @classmethod
    def validate_color(cls, v: str) -> str:
        return v.upper()


class TagCreate(TagBase):
    """Schema for creating a Tag."""

    workspace_id: UUID | None = None


class TagUpdate(BaseModel):
    """Schema for updating a Tag."""

    name: str | None = Field(None, min_length=1, max_length=50)
    color_hex: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class TagResponse(BaseModel):
    """Schema for Tag response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "456e4567-e89b-12d3-a456-426614174000",
                "name": "work",
                "color_hex": "#3B82F6",
                "created_at": "2026-01-28T10:00:00",
                "usage_count": 5,
            }
        },
    )

    id: UUID
    name: str
    color_hex: str
    workspace_id: UUID | None = None
    created_at: datetime
    usage_count: int = 0


class TagListResponse(BaseModel):
    """Schema for list of Tags."""

    data: list[TagResponse]


class TagDetailResponse(BaseModel):
    """Schema for single Tag."""

    data: TagResponse


class TodoTagAttach(BaseModel):
    """Schema for attaching tag to todo."""

    tag_id: UUID


class TodoTagResponse(BaseModel):
    """Schema for todo-tag relationship."""

    todo_id: UUID
    tag_id: UUID
    attached_at: datetime
