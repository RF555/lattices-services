"""Common Pydantic schemas shared across the API."""

from typing import Any

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error_code: str
    message: str
    details: Any | None = None


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
