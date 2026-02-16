"""Unit tests for exception handlers."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.exception_handlers import setup_exception_handlers
from core.exceptions import TodoNotFoundError


def _create_test_app() -> FastAPI:
    app = FastAPI()
    setup_exception_handlers(app)
    return app


class TestExceptionHandlers:
    @pytest.mark.asyncio
    async def test_app_exception_returns_error_code_and_message(self) -> None:
        app = _create_test_app()

        @app.get("/raise-app")
        async def _() -> None:
            raise TodoNotFoundError("some-id")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/raise-app")

        assert response.status_code == 404
        body = response.json()
        assert body["error_code"] == "TASK_NOT_FOUND"
        assert "some-id" in body["message"]
        assert body["details"]["todo_id"] == "some-id"

    @pytest.mark.asyncio
    async def test_http_exception_returns_standard_format(self) -> None:
        from starlette.exceptions import HTTPException

        app = _create_test_app()

        @app.get("/raise-http")
        async def _() -> None:
            raise HTTPException(status_code=403, detail="Forbidden")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.get("/raise-http")

        assert response.status_code == 403
        body = response.json()
        assert body["error_code"] == "HTTP_ERROR"
        assert body["message"] == "Forbidden"

    @pytest.mark.asyncio
    async def test_validation_error_returns_field_details(self) -> None:
        from pydantic import BaseModel, Field

        app = _create_test_app()

        class Body(BaseModel):
            title: str = Field(..., min_length=1)

        @app.post("/validate")
        async def _(body: Body) -> dict[str, bool]:
            return {"ok": True}

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            response = await c.post("/validate", json={"title": ""})

        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert isinstance(body["details"], list)
        assert len(body["details"]) >= 1

    @pytest.mark.asyncio
    async def test_unhandled_exception_returns_500(self) -> None:
        import json
        from unittest.mock import MagicMock

        app = _create_test_app()

        # Build a fake request with request.state.request_id
        mock_request = MagicMock()
        mock_request.state.request_id = "test-req-id"

        exc = RuntimeError("Something went wrong")

        # Get the registered handler by looking up the app's handlers
        handler = None
        for exc_class, h in app.exception_handlers.items():
            if exc_class is Exception:
                handler = h
                break

        assert handler is not None, "Global exception handler not registered"

        response = await handler(mock_request, exc)  # type: ignore[misc]

        assert response.status_code == 500
        body = json.loads(response.body)
        assert body["error_code"] == "INTERNAL_ERROR"
        assert body["details"]["request_id"] == "test-req-id"
