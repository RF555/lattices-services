"""Unit tests for JWTAuthProvider ES256/JWKS paths.

Covers the previously untested code in jwt_provider.py:
- _get_jwks_keys() fetching, caching, and error handling
- _validate_es256() with mocked JWKS endpoint
- validate_token returning None when payload lacks sub or email
- __init__ with ES256 algorithm configuration
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from jose import jwt as jose_jwt

from infrastructure.auth import jwt_provider as jwt_provider_module
from infrastructure.auth.jwt_provider import JWTAuthProvider, _get_jwks_keys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hs256_token(payload: dict[str, Any], secret: str = "test-secret") -> str:
    return str(jose_jwt.encode(payload, secret, algorithm="HS256"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_jwks_cache() -> Generator[None, None, None]:
    jwt_provider_module._jwks_cache = None
    yield
    jwt_provider_module._jwks_cache = None


@pytest.fixture
def hs256_provider() -> JWTAuthProvider:
    return JWTAuthProvider(secret_key="test-secret", algorithm="HS256", expire_minutes=30)


# ---------------------------------------------------------------------------
# Tests: validate_token returns None for missing claims
# ---------------------------------------------------------------------------


class TestValidateTokenMissingClaims:
    async def test_should_return_none_when_token_has_no_sub_claim(
        self, hs256_provider: JWTAuthProvider
    ) -> None:
        token = _make_hs256_token({"email": "user@example.com", "exp": 9999999999})

        result = await hs256_provider.validate_token(token)

        assert result is None

    async def test_should_return_none_when_token_has_no_email_claim(
        self, hs256_provider: JWTAuthProvider
    ) -> None:
        token = _make_hs256_token({"sub": str(uuid4()), "exp": 9999999999})

        result = await hs256_provider.validate_token(token)

        assert result is None

    async def test_should_return_none_when_token_has_empty_sub(
        self, hs256_provider: JWTAuthProvider
    ) -> None:
        token = _make_hs256_token({"sub": "", "email": "user@example.com", "exp": 9999999999})

        result = await hs256_provider.validate_token(token)

        assert result is None

    async def test_should_return_none_when_token_has_empty_email(
        self, hs256_provider: JWTAuthProvider
    ) -> None:
        token = _make_hs256_token({"sub": str(uuid4()), "email": "", "exp": 9999999999})

        result = await hs256_provider.validate_token(token)

        assert result is None


# ---------------------------------------------------------------------------
# Tests: _get_jwks_keys
# ---------------------------------------------------------------------------


class TestGetJwksKeys:
    async def test_should_return_empty_dict_when_no_supabase_url(self) -> None:
        with patch.object(jwt_provider_module, "settings", create=True) as mock_settings:
            mock_settings.supabase_jwks_url = ""

            result = await _get_jwks_keys()

            assert result == {}

    async def test_should_fetch_and_cache_jwks_keys(self) -> None:
        fake_jwks = {
            "keys": [
                {"kid": "key-1", "kty": "EC", "crv": "P-256", "x": "aa", "y": "bb"},
                {"kid": "key-2", "kty": "EC", "crv": "P-256", "x": "cc", "y": "dd"},
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = fake_jwks
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(jwt_provider_module, "settings", create=True) as mock_settings,
            patch.object(jwt_provider_module, "httpx") as mock_httpx,
        ):
            mock_settings.supabase_jwks_url = (
                "https://example.supabase.co/auth/v1/.well-known/jwks.json"
            )
            mock_httpx.AsyncClient.return_value = mock_client_instance

            result = await _get_jwks_keys()

            assert "key-1" in result
            assert "key-2" in result
            assert result["key-1"]["kty"] == "EC"

            # Verify caching: second call should NOT trigger another HTTP request
            mock_client_instance.get.reset_mock()
            cached_result = await _get_jwks_keys()
            mock_client_instance.get.assert_not_called()
            assert cached_result == result

    async def test_should_return_empty_dict_on_http_error(self) -> None:
        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = Exception("Connection refused")
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(jwt_provider_module, "settings", create=True) as mock_settings,
            patch.object(jwt_provider_module, "httpx") as mock_httpx,
        ):
            mock_settings.supabase_jwks_url = (
                "https://example.supabase.co/auth/v1/.well-known/jwks.json"
            )
            mock_httpx.AsyncClient.return_value = mock_client_instance

            result = await _get_jwks_keys()

            assert result == {}

    async def test_should_skip_keys_without_kid(self) -> None:
        fake_jwks = {
            "keys": [
                {"kty": "EC", "crv": "P-256", "x": "aa", "y": "bb"},  # no kid
                {"kid": "good-key", "kty": "EC", "crv": "P-256", "x": "cc", "y": "dd"},
            ]
        }
        mock_response = MagicMock()
        mock_response.json.return_value = fake_jwks
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response
        mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
        mock_client_instance.__aexit__ = AsyncMock(return_value=False)

        with (
            patch.object(jwt_provider_module, "settings", create=True) as mock_settings,
            patch.object(jwt_provider_module, "httpx") as mock_httpx,
        ):
            mock_settings.supabase_jwks_url = (
                "https://example.supabase.co/auth/v1/.well-known/jwks.json"
            )
            mock_httpx.AsyncClient.return_value = mock_client_instance

            result = await _get_jwks_keys()

            assert len(result) == 1
            assert "good-key" in result


# ---------------------------------------------------------------------------
# Tests: _validate_es256
# ---------------------------------------------------------------------------


class TestValidateEs256:
    async def test_should_return_none_when_header_has_no_kid(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        result = await provider._validate_es256(
            token="dummy.token.value",
            header={"alg": "ES256"},  # no kid
        )

        assert result is None

    async def test_should_return_none_when_kid_not_found_in_jwks(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        # Mock _get_jwks_keys to return keys that don't match the requested kid
        with patch.object(
            jwt_provider_module, "_get_jwks_keys", new_callable=AsyncMock
        ) as mock_get_jwks:
            mock_get_jwks.return_value = {"other-kid": {"kty": "EC"}}

            result = await provider._validate_es256(
                token="dummy.token.value",
                header={"alg": "ES256", "kid": "missing-kid"},
            )

            assert result is None
            # Should have been called twice: initial lookup + refetch after cache clear
            assert mock_get_jwks.call_count == 2

    async def test_should_decode_token_when_kid_found_in_jwks(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        fake_key_data: dict[str, Any] = {"kid": "test-kid", "kty": "EC", "crv": "P-256"}
        fake_payload: dict[str, Any] = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "exp": 9999999999,
        }

        with (
            patch.object(
                jwt_provider_module, "_get_jwks_keys", new_callable=AsyncMock
            ) as mock_get_jwks,
            patch.object(jwt_provider_module, "ECKey") as mock_eckey_cls,
            patch.object(jwt_provider_module, "jwt") as mock_jwt,
        ):
            mock_get_jwks.return_value = {"test-kid": fake_key_data}
            mock_ec_instance = MagicMock()
            mock_eckey_cls.return_value = mock_ec_instance
            mock_jwt.decode.return_value = fake_payload

            result = await provider._validate_es256(
                token="es256.token.value",
                header={"alg": "ES256", "kid": "test-kid"},
            )

            assert result == fake_payload
            mock_eckey_cls.assert_called_once_with(fake_key_data, algorithm="ES256")
            mock_jwt.decode.assert_called_once_with(
                "es256.token.value",
                mock_ec_instance,
                algorithms=["ES256"],
                options={"verify_aud": False},
            )

    async def test_should_refetch_jwks_and_succeed_on_key_rotation(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        fake_key_data: dict[str, Any] = {"kid": "rotated-kid", "kty": "EC", "crv": "P-256"}
        fake_payload: dict[str, Any] = {
            "sub": str(uuid4()),
            "email": "rotated@example.com",
        }

        call_count = 0

        async def mock_get_jwks_side_effect() -> dict[str, Any]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {}  # first call: key not found
            return {"rotated-kid": fake_key_data}  # second call: key found after rotation

        with (
            patch.object(
                jwt_provider_module,
                "_get_jwks_keys",
                new_callable=AsyncMock,
                side_effect=mock_get_jwks_side_effect,
            ),
            patch.object(jwt_provider_module, "ECKey") as mock_eckey_cls,
            patch.object(jwt_provider_module, "jwt") as mock_jwt,
        ):
            mock_ec_instance = MagicMock()
            mock_eckey_cls.return_value = mock_ec_instance
            mock_jwt.decode.return_value = fake_payload

            result = await provider._validate_es256(
                token="rotated.token.value",
                header={"alg": "ES256", "kid": "rotated-kid"},
            )

            assert result == fake_payload
            assert call_count == 2


# ---------------------------------------------------------------------------
# Tests: __init__ with ES256 configuration
# ---------------------------------------------------------------------------


class TestJWTAuthProviderInit:
    def test_should_store_es256_algorithm(self) -> None:
        provider = JWTAuthProvider(
            secret_key="not-used-for-es256",
            algorithm="ES256",
            expire_minutes=60,
        )

        assert provider._algorithm == "ES256"
        assert provider._expire_minutes == 60
        assert provider._secret_key == "not-used-for-es256"

    def test_should_store_hs256_algorithm_by_default(self) -> None:
        provider = JWTAuthProvider(
            secret_key="my-secret",
            algorithm="HS256",
            expire_minutes=15,
        )

        assert provider._algorithm == "HS256"
        assert provider._secret_key == "my-secret"
        assert provider._expire_minutes == 15


# ---------------------------------------------------------------------------
# Tests: validate_token ES256 integration (mocked end-to-end)
# ---------------------------------------------------------------------------


class TestValidateTokenEs256Path:
    async def test_should_delegate_to_validate_es256_for_es256_token(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        user_id = str(uuid4())
        fake_payload: dict[str, Any] = {
            "sub": user_id,
            "email": "es256user@example.com",
            "user_metadata": {"display_name": "ES256 User"},
            "role": "authenticated",
        }

        # Build a dummy token whose header contains alg=ES256
        with (
            patch.object(jwt_provider_module, "jwt") as mock_jwt,
        ):
            mock_jwt.get_unverified_header.return_value = {"alg": "ES256", "kid": "k1"}
            # Make _validate_es256 return the fake payload
            mock_jwt.JWTError = jose_jwt.JWTError  # preserve exception class for except block

            with patch.object(provider, "_validate_es256", new_callable=AsyncMock) as mock_es256:
                mock_es256.return_value = fake_payload

                result = await provider.validate_token("es256.token.here")

                mock_es256.assert_called_once_with(
                    "es256.token.here",
                    {"alg": "ES256", "kid": "k1"},
                )
                assert result is not None
                assert result.email == "es256user@example.com"
                assert result.display_name == "ES256 User"
                assert result.role == "authenticated"
                assert str(result.id) == user_id

    async def test_should_return_none_when_es256_validation_returns_none(self) -> None:
        provider = JWTAuthProvider(secret_key="unused", algorithm="HS256", expire_minutes=30)

        with patch.object(jwt_provider_module, "jwt") as mock_jwt:
            mock_jwt.get_unverified_header.return_value = {"alg": "ES256", "kid": "k1"}
            mock_jwt.JWTError = jose_jwt.JWTError

            with patch.object(provider, "_validate_es256", new_callable=AsyncMock) as mock_es256:
                mock_es256.return_value = None

                result = await provider.validate_token("es256.token.here")

                assert result is None
