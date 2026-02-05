"""Unit tests for authentication dependencies."""

from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from api.dependencies.auth import get_current_user, get_optional_user
from core.exceptions import AuthenticationError, ErrorCode
from infrastructure.auth.jwt_provider import JWTAuthProvider
from infrastructure.auth.provider import TokenUser


@pytest.fixture
def mock_auth_provider() -> JWTAuthProvider:
    provider = JWTAuthProvider(secret_key="test-secret", algorithm="HS256", expire_minutes=30)
    return provider


@pytest.fixture
def test_token_user() -> TokenUser:
    return TokenUser(id=uuid4(), email="test@example.com", display_name="Test User")


# --- get_current_user ---


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_with_valid_token(
        self, mock_auth_provider: JWTAuthProvider, test_token_user: TokenUser
    ):
        token = mock_auth_provider.create_token(test_token_user)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        result = await get_current_user(credentials, mock_auth_provider)

        assert result.email == test_token_user.email
        assert result.id == test_token_user.id

    @pytest.mark.asyncio
    async def test_raises_when_no_credentials(self, mock_auth_provider: JWTAuthProvider):
        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(None, mock_auth_provider)

        assert exc_info.value.error_code == ErrorCode.UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_raises_when_invalid_token(self, mock_auth_provider: JWTAuthProvider):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.jwt.token")

        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(credentials, mock_auth_provider)

        assert exc_info.value.error_code == ErrorCode.INVALID_TOKEN

    @pytest.mark.asyncio
    async def test_raises_when_expired_token(self, test_token_user: TokenUser):
        # Create provider with 0 expiry to generate expired tokens
        provider = JWTAuthProvider(secret_key="test-secret", algorithm="HS256", expire_minutes=-1)
        token = provider.create_token(test_token_user)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        # Use normal provider for validation
        normal_provider = JWTAuthProvider(
            secret_key="test-secret", algorithm="HS256", expire_minutes=30
        )

        with pytest.raises(AuthenticationError) as exc_info:
            await get_current_user(credentials, normal_provider)

        assert exc_info.value.error_code == ErrorCode.INVALID_TOKEN


# --- get_optional_user ---


class TestGetOptionalUser:
    @pytest.mark.asyncio
    async def test_returns_user_with_valid_token(
        self, mock_auth_provider: JWTAuthProvider, test_token_user: TokenUser
    ):
        token = mock_auth_provider.create_token(test_token_user)
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

        result = await get_optional_user(credentials, mock_auth_provider)

        assert result is not None
        assert result.email == test_token_user.email

    @pytest.mark.asyncio
    async def test_returns_none_when_no_credentials(self, mock_auth_provider: JWTAuthProvider):
        result = await get_optional_user(None, mock_auth_provider)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_invalid_token(self, mock_auth_provider: JWTAuthProvider):
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.jwt.token")

        result = await get_optional_user(credentials, mock_auth_provider)
        assert result is None
