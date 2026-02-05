"""Authentication dependencies for FastAPI."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.exceptions import AuthenticationError, ErrorCode
from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser

# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)

# Singleton auth provider
_auth_provider: JWTAuthProvider | None = None


def get_auth_provider() -> JWTAuthProvider:
    """Get or create the auth provider singleton."""
    global _auth_provider
    if _auth_provider is None:
        _auth_provider = JWTAuthProvider()
    return _auth_provider


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
    auth_provider: JWTAuthProvider = Depends(get_auth_provider),
) -> TokenUser:
    """
    Dependency to get the current authenticated user.

    Raises:
        AuthenticationError: If no token provided or token is invalid
    """
    if not credentials:
        raise AuthenticationError(
            message="Authorization header required",
            error_code=ErrorCode.UNAUTHORIZED,
        )

    token = credentials.credentials
    user = await auth_provider.validate_token(token)

    if not user:
        raise AuthenticationError(
            message="Invalid or expired token",
            error_code=ErrorCode.INVALID_TOKEN,
        )

    return user


async def get_optional_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(security),
    ],
    auth_provider: JWTAuthProvider = Depends(get_auth_provider),
) -> TokenUser | None:
    """
    Dependency to get the current user if authenticated.

    Returns:
        TokenUser if authenticated, None otherwise (no exception raised)
    """
    if not credentials:
        return None

    return await auth_provider.validate_token(credentials.credentials)


# Type alias for convenience in route handlers
CurrentUser = Annotated[TokenUser, Depends(get_current_user)]
OptionalUser = Annotated[TokenUser | None, Depends(get_optional_user)]


async def get_workspace_id_from_header(
    x_workspace_id: Annotated[str | None, Header()] = None,
) -> UUID | None:
    """Extract workspace ID from X-Workspace-Id header if present."""
    if x_workspace_id:
        try:
            return UUID(x_workspace_id)
        except ValueError:
            return None
    return None


WorkspaceId = Annotated[UUID | None, Depends(get_workspace_id_from_header)]
