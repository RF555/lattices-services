"""Pydantic schemas for Todo API."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TodoBase(BaseModel):
    """Base schema for Todo."""

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    parent_id: UUID | None = None


class TodoCreate(TodoBase):
    """Schema for creating a Todo."""

    workspace_id: UUID | None = None


class TodoUpdate(BaseModel):
    """Schema for updating a Todo (all fields optional)."""

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=1000)
    is_completed: bool | None = None
    parent_id: UUID | None = None
    position: int | None = Field(None, ge=0)


class TagSummary(BaseModel):
    """Minimal tag representation for embedding in Todo response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    color_hex: str


class TodoResponse(BaseModel):
    """Schema for Todo response."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "parent_id": None,
                "title": "Complete project documentation",
                "description": "Write comprehensive docs for the API",
                "is_completed": False,
                "position": 0,
                "created_at": "2026-01-28T10:00:00",
                "updated_at": "2026-01-28T10:00:00",
                "completed_at": None,
                "tags": [
                    {
                        "id": "456e4567-e89b-12d3-a456-426614174000",
                        "name": "documentation",
                        "color_hex": "#10B981",
                    }
                ],
                "child_count": 0,
                "completed_child_count": 0,
            }
        },
    )

    id: UUID
    parent_id: UUID | None
    workspace_id: UUID | None = None
    title: str
    description: str | None
    is_completed: bool
    position: int
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    tags: list[TagSummary] = []
    child_count: int = 0
    completed_child_count: int = 0


class TodoListResponse(BaseModel):
    """Schema for list of Todos response."""

    data: list[TodoResponse]
    meta: dict[str, Any] = Field(default_factory=dict)


class TodoDetailResponse(BaseModel):
    """Schema for single Todo response."""

    data: TodoResponse
