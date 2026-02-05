"""Rate limiting configuration using slowapi."""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    enabled=settings.rate_limit_enabled,
)


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle rate limit exceeded errors."""
    detail = exc.detail if isinstance(exc, RateLimitExceeded) else str(exc)
    return JSONResponse(
        status_code=429,
        content={
            "error_code": "RATE_LIMIT_EXCEEDED",
            "message": f"Rate limit exceeded: {detail}",
            "details": {
                "retry_after": str(detail),
            },
        },
    )
