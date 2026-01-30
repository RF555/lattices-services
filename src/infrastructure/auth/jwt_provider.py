"""JWT authentication provider implementation.

Supports both Supabase-issued JWTs (ES256 via JWKS) and
locally-created tokens (HS256 for tests).

Supabase JWT payload structure:
    {
        "sub": "user-uuid",
        "email": "user@example.com",
        "role": "authenticated",
        "aud": "authenticated",
        "user_metadata": { "display_name": "John" },
        "exp": 1234567890
    }
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

import httpx
from jose import JWTError, jwt
from jose.backends import ECKey

from core.config import settings
from infrastructure.auth.provider import TokenUser

logger = logging.getLogger(__name__)

# Module-level JWKS cache (fetched once, reused across requests)
_jwks_cache: dict[str, Any] | None = None


async def _get_jwks_keys() -> dict[str, Any]:
    """Fetch and cache JWKS keys from Supabase."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    jwks_url = settings.supabase_jwks_url
    if not jwks_url:
        return {}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(jwks_url, timeout=10.0)
            response.raise_for_status()
            jwks_data = response.json()
            # Build a kid -> key mapping
            _jwks_cache = {}
            for key_data in jwks_data.get("keys", []):
                kid = key_data.get("kid")
                if kid:
                    _jwks_cache[kid] = key_data
            logger.info("Fetched %d JWKS keys from Supabase", len(_jwks_cache))
            return _jwks_cache
    except Exception:
        logger.exception("Failed to fetch JWKS from %s", jwks_url)
        return {}


class JWTAuthProvider:
    """JWT-based authentication provider.

    Handles validation of both Supabase-issued (ES256) and
    locally-created (HS256) JWTs.
    """

    def __init__(
        self,
        secret_key: str = settings.jwt_secret_key,
        algorithm: str = settings.jwt_algorithm,
        expire_minutes: int = settings.jwt_expire_minutes,
    ) -> None:
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    async def validate_token(self, token: str) -> Optional[TokenUser]:
        """
        Validate a JWT token and extract user info.

        Detects the signing algorithm from the token header:
        - ES256 (Supabase): validates via JWKS public key
        - HS256 (local/test): validates via shared secret

        Args:
            token: The JWT to validate

        Returns:
            TokenUser if valid, None if invalid or expired
        """
        try:
            header = jwt.get_unverified_header(token)
            alg = header.get("alg", self._algorithm)

            if alg == "ES256":
                payload = await self._validate_es256(token, header)
            else:
                payload = jwt.decode(
                    token,
                    self._secret_key,
                    algorithms=[self._algorithm],
                    options={"verify_aud": False},
                )

            if payload is None:
                return None

            user_id = payload.get("sub")
            email = payload.get("email")

            if not user_id or not email:
                return None

            # Supabase stores display name in user_metadata
            user_metadata = payload.get("user_metadata") or {}
            display_name = (
                user_metadata.get("display_name")
                or user_metadata.get("name")
                or user_metadata.get("full_name")
                or payload.get("name")
            )

            role = payload.get("role")

            return TokenUser(
                id=UUID(user_id),
                email=email,
                display_name=display_name,
                role=role,
            )

        except JWTError:
            return None

    async def _validate_es256(
        self, token: str, header: dict
    ) -> Optional[dict]:
        """Validate an ES256-signed JWT using JWKS public keys."""
        kid = header.get("kid")
        if not kid:
            return None

        jwks_keys = await _get_jwks_keys()
        key_data = jwks_keys.get(kid)
        if not key_data:
            # Key not found — try refetching JWKS (key rotation)
            global _jwks_cache
            _jwks_cache = None
            jwks_keys = await _get_jwks_keys()
            key_data = jwks_keys.get(kid)
            if not key_data:
                logger.warning("JWKS key not found for kid=%s", kid)
                return None

        ec_key = ECKey(key_data, algorithm="ES256")
        return jwt.decode(
            token,
            ec_key,
            algorithms=["ES256"],
            options={"verify_aud": False},
        )

    def create_token(self, user: TokenUser) -> str:
        """
        Create a JWT token for a user (HS256, used for tests).

        Args:
            user: The user to create a token for

        Returns:
            The generated JWT string
        """
        expire = datetime.utcnow() + timedelta(minutes=self._expire_minutes)

        payload: dict = {
            "sub": str(user.id),
            "email": user.email,
            "aud": "authenticated",
            "role": "authenticated",
            "exp": expire,
            "user_metadata": {
                "display_name": user.display_name,
            },
        }

        return jwt.encode(payload, self._secret_key, algorithm=self._algorithm)
