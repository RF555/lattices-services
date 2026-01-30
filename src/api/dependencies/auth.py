"""Authentication dependencies for FastAPI."""

from typing import Annotated, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.exceptions import AuthenticationError, ErrorCode
from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser


# Security scheme for OpenAPI docs
security = HTTPBearer(auto_error=False)

# Singleton auth provider
_auth_provider: Optional[JWTAuthProvider] = None


def get_auth_provider() -> JWTAuthProvider:
    """Get or create the auth provider singleton."""
    global _auth_provider
    if _auth_provider is None:
        _auth_provider = JWTAuthProvider()
    return _auth_provider


async def get_current_user(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
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
        Optional[HTTPAuthorizationCredentials],
        Depends(security),
    ],
    auth_provider: JWTAuthProvider = Depends(get_auth_provider),
) -> Optional[TokenUser]:
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
OptionalUser = Annotated[Optional[TokenUser], Depends(get_optional_user)]
