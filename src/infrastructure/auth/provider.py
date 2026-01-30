"""Authentication provider protocol."""

from dataclasses import dataclass
from typing import Optional, Protocol
from uuid import UUID


@dataclass
class TokenUser:
    """Represents a user extracted from an auth token."""

    id: UUID
    email: str
    display_name: Optional[str] = None
    role: Optional[str] = None


class IAuthProvider(Protocol):
    """Protocol for authentication providers."""

    async def validate_token(self, token: str) -> Optional[TokenUser]:
        """
        Validate an authentication token.

        Args:
            token: The bearer token to validate

        Returns:
            TokenUser if valid, None if invalid
        """
        ...

    def create_token(self, user: TokenUser) -> str:
        """
        Create an authentication token for a user.

        Args:
            user: The user to create a token for

        Returns:
            The generated token string
        """
        ...
