"""Common Pydantic schemas shared across the API."""

from typing import Any, Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Standardized error response."""

    error_code: str
    message: str
    details: Optional[Any] = None


class MessageResponse(BaseModel):
    """Simple message response."""

    message: str
