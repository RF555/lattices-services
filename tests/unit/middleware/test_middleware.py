"""Unit tests for middleware."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.middleware.request_id import RequestIDMiddleware
from api.middleware.security import SecurityHeadersMiddleware


def _create_app_with_middleware() -> FastAPI:
    """Create a minimal FastAPI app with security and request ID middleware."""
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    @app.get("/test")
    async def _():
        return {"ok": True}

    return app


class TestSecurityHeadersMiddleware:
    """Tests for SecurityHeadersMiddleware."""

    @pytest.mark.asyncio
    async def test_adds_x_content_type_options(self):
        """Response includes X-Content-Type-Options: nosniff."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/test")

        assert response.headers["x-content-type-options"] == "nosniff"

    @pytest.mark.asyncio
    async def test_adds_x_frame_options(self):
        """Response includes X-Frame-Options: DENY."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/test")

        assert response.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_adds_referrer_policy(self):
        """Response includes Referrer-Policy header."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/test")

        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


class TestRequestIDMiddleware:
    """Tests for RequestIDMiddleware."""

    @pytest.mark.asyncio
    async def test_generates_request_id_when_not_provided(self):
        """Response includes a generated X-Request-ID header."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/test")

        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) > 0

    @pytest.mark.asyncio
    async def test_propagates_existing_request_id(self):
        """Provided X-Request-ID is propagated to response."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/test", headers={"X-Request-ID": "custom-req-123"})

        assert response.headers["x-request-id"] == "custom-req-123"

    @pytest.mark.asyncio
    async def test_request_id_in_response_header(self):
        """X-Request-ID is always present in the response."""
        app = _create_app_with_middleware()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r1 = await c.get("/test")
            r2 = await c.get("/test")

        # Both responses have request IDs
        assert "x-request-id" in r1.headers
        assert "x-request-id" in r2.headers
        # Auto-generated IDs should differ
        assert r1.headers["x-request-id"] != r2.headers["x-request-id"]
