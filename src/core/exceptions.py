"""Custom exceptions and error codes."""

from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    """Standardized error codes for the API."""

    # Authentication errors (401)
    UNAUTHORIZED = "UNAUTHORIZED"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"

    # Authorization errors (403)
    FORBIDDEN = "FORBIDDEN"

    # Not found errors (404)
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TAG_NOT_FOUND = "TAG_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"

    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CIRCULAR_REFERENCE = "CIRCULAR_REFERENCE"

    # Conflict errors (409)
    DUPLICATE_TAG = "DUPLICATE_TAG"

    # Rate limiting (429)
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"

    # Server errors (500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str,
        status_code: int = 400,
        details: Optional[Any] = None,
    ) -> None:
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class AuthenticationError(AppException):
    """Authentication failed."""

    def __init__(
        self,
        message: str = "Authentication required",
        error_code: ErrorCode = ErrorCode.UNAUTHORIZED,
    ) -> None:
        super().__init__(
            error_code=error_code,
            message=message,
            status_code=401,
        )


class AuthorizationError(AppException):
    """Authorization failed."""

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(
            error_code=ErrorCode.FORBIDDEN,
            message=message,
            status_code=403,
        )


class TodoNotFoundError(AppException):
    """Todo not found."""

    def __init__(self, todo_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.TASK_NOT_FOUND,
            message=f"Task not found: {todo_id}",
            status_code=404,
            details={"todo_id": todo_id},
        )


class TagNotFoundError(AppException):
    """Tag not found."""

    def __init__(self, tag_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.TAG_NOT_FOUND,
            message=f"Tag not found: {tag_id}",
            status_code=404,
            details={"tag_id": tag_id},
        )


class CircularReferenceError(AppException):
    """Circular reference detected in hierarchy."""

    def __init__(self, message: str = "Circular reference detected") -> None:
        super().__init__(
            error_code=ErrorCode.CIRCULAR_REFERENCE,
            message=message,
            status_code=400,
        )
