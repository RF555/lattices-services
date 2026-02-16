"""Custom exceptions and error codes."""

from enum import StrEnum
from typing import Any


class ErrorCode(StrEnum):
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
    WORKSPACE_NOT_FOUND = "WORKSPACE_NOT_FOUND"

    # Validation errors (400)
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CIRCULAR_REFERENCE = "CIRCULAR_REFERENCE"
    INVALID_ROLE = "INVALID_ROLE"
    LAST_OWNER = "LAST_OWNER"
    LAST_WORKSPACE = "LAST_WORKSPACE"
    WORKSPACE_MOVE_INVALID = "WORKSPACE_MOVE_INVALID"

    # Authorization errors (403) - workspace-specific
    NOT_A_MEMBER = "NOT_A_MEMBER"
    INSUFFICIENT_PERMISSIONS = "INSUFFICIENT_PERMISSIONS"

    # Invitation errors
    INVITATION_NOT_FOUND = "INVITATION_NOT_FOUND"
    INVITATION_EXPIRED = "INVITATION_EXPIRED"
    INVITATION_ALREADY_ACCEPTED = "INVITATION_ALREADY_ACCEPTED"
    DUPLICATE_INVITATION = "DUPLICATE_INVITATION"
    INVITATION_EMAIL_MISMATCH = "INVITATION_EMAIL_MISMATCH"

    # Group errors
    GROUP_NOT_FOUND = "GROUP_NOT_FOUND"
    GROUP_MEMBER_NOT_FOUND = "GROUP_MEMBER_NOT_FOUND"
    ALREADY_A_GROUP_MEMBER = "ALREADY_A_GROUP_MEMBER"

    # Notification errors
    NOTIFICATION_NOT_FOUND = "NOTIFICATION_NOT_FOUND"
    NOTIFICATION_RECIPIENT_NOT_FOUND = "NOTIFICATION_RECIPIENT_NOT_FOUND"

    # Conflict errors (409)
    DUPLICATE_TAG = "DUPLICATE_TAG"
    WORKSPACE_SLUG_TAKEN = "WORKSPACE_SLUG_TAKEN"
    ALREADY_A_MEMBER = "ALREADY_A_MEMBER"

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
        details: Any | None = None,
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


class WorkspaceNotFoundError(AppException):
    """Workspace not found."""

    def __init__(self, workspace_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.WORKSPACE_NOT_FOUND,
            message=f"Workspace not found: {workspace_id}",
            status_code=404,
            details={"workspace_id": workspace_id},
        )


class NotAMemberError(AppException):
    """User is not a member of the workspace."""

    def __init__(self, workspace_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.NOT_A_MEMBER,
            message="You are not a member of this workspace",
            status_code=403,
            details={"workspace_id": workspace_id},
        )


class InsufficientPermissionsError(AppException):
    """User does not have sufficient permissions."""

    def __init__(self, required_role: str = "admin") -> None:
        super().__init__(
            error_code=ErrorCode.INSUFFICIENT_PERMISSIONS,
            message=f"Insufficient permissions. Required role: {required_role}",
            status_code=403,
            details={"required_role": required_role},
        )


class LastOwnerError(AppException):
    """Cannot remove or demote the last owner of a workspace."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ErrorCode.LAST_OWNER,
            message="Cannot remove or demote the last owner of a workspace",
            status_code=400,
        )


class LastWorkspaceError(AppException):
    """Cannot delete or leave the user's last workspace."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ErrorCode.LAST_WORKSPACE,
            message="Cannot delete or leave your last workspace",
            status_code=400,
        )


class WorkspaceSlugTakenError(AppException):
    """Workspace slug is already taken."""

    def __init__(self, slug: str) -> None:
        super().__init__(
            error_code=ErrorCode.WORKSPACE_SLUG_TAKEN,
            message=f"Workspace slug already taken: {slug}",
            status_code=409,
            details={"slug": slug},
        )


class AlreadyAMemberError(AppException):
    """User is already a member of the workspace."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.ALREADY_A_MEMBER,
            message="User is already a member of this workspace",
            status_code=409,
            details={"user_id": user_id},
        )


class InvitationNotFoundError(AppException):
    """Invitation not found."""

    def __init__(self, invitation_id: str = "") -> None:
        super().__init__(
            error_code=ErrorCode.INVITATION_NOT_FOUND,
            message="Invitation not found",
            status_code=404,
            details={"invitation_id": invitation_id} if invitation_id else None,
        )


class InvitationExpiredError(AppException):
    """Invitation has expired."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ErrorCode.INVITATION_EXPIRED,
            message="This invitation has expired",
            status_code=400,
        )


class InvitationAlreadyAcceptedError(AppException):
    """Invitation has already been accepted."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ErrorCode.INVITATION_ALREADY_ACCEPTED,
            message="This invitation has already been accepted",
            status_code=400,
        )


class DuplicateInvitationError(AppException):
    """A pending invitation already exists for this email and workspace."""

    def __init__(self, email: str) -> None:
        super().__init__(
            error_code=ErrorCode.DUPLICATE_INVITATION,
            message="A pending invitation already exists for this email",
            status_code=409,
            details={"email": email},
        )


class InvitationEmailMismatchError(AppException):
    """The user's email does not match the invitation email."""

    def __init__(self) -> None:
        super().__init__(
            error_code=ErrorCode.INVITATION_EMAIL_MISMATCH,
            message="Your email does not match the invitation email",
            status_code=403,
        )


class GroupNotFoundError(AppException):
    """Group not found."""

    def __init__(self, group_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.GROUP_NOT_FOUND,
            message=f"Group not found: {group_id}",
            status_code=404,
            details={"group_id": group_id},
        )


class AlreadyAGroupMemberError(AppException):
    """User is already a member of the group."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.ALREADY_A_GROUP_MEMBER,
            message="User is already a member of this group",
            status_code=409,
            details={"user_id": user_id},
        )


class GroupMemberNotFoundError(AppException):
    """Group member not found."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.GROUP_MEMBER_NOT_FOUND,
            message="User is not a member of this group",
            status_code=404,
            details={"user_id": user_id},
        )


class NotificationNotFoundError(AppException):
    """Notification not found."""

    def __init__(self, notification_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.NOTIFICATION_NOT_FOUND,
            message=f"Notification not found: {notification_id}",
            status_code=404,
            details={"notification_id": notification_id},
        )


class NotificationRecipientNotFoundError(AppException):
    """Notification recipient not found."""

    def __init__(self, recipient_id: str) -> None:
        super().__init__(
            error_code=ErrorCode.NOTIFICATION_RECIPIENT_NOT_FOUND,
            message=f"Notification recipient not found: {recipient_id}",
            status_code=404,
            details={"recipient_id": recipient_id},
        )
