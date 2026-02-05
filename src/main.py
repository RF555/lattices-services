"""Main FastAPI application entry point."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from api.exception_handlers import setup_exception_handlers
from api.middleware.logging import RequestLoggingMiddleware
from api.middleware.request_id import RequestIDMiddleware
from api.middleware.security import SecurityHeadersMiddleware
from api.routes.health import router as health_router
from api.v1 import router as v1_router
from api.v1.dependencies import get_notification_service
from core.config import settings
from core.logging import setup_logging
from core.rate_limit import limiter, rate_limit_exceeded_handler

logger = structlog.get_logger()

# Initialize structured logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager for startup/shutdown tasks."""

    async def notification_cleanup_loop() -> None:
        """Periodically clean up expired notifications.

        Note: For production, prefer using pg_cron in Supabase Dashboard:
        SELECT cron.schedule('cleanup-expired-notifications', '0 3 * * 0',
            $$DELETE FROM notifications
              WHERE expires_at IS NOT NULL AND expires_at < NOW()$$
        );
        """
        while True:
            await asyncio.sleep(86400)  # Run once per day
            try:
                service = get_notification_service()
                deleted = await service.cleanup_expired()
                if deleted > 0:
                    logger.info(
                        "notification_cleanup_completed",
                        deleted_count=deleted,
                    )
            except Exception:
                logger.exception("notification_cleanup_failed")

    cleanup_task = asyncio.create_task(notification_cleanup_loop())
    yield
    cleanup_task.cancel()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        lifespan=lifespan,
        default_response_class=ORJSONResponse,
        title=settings.app_name,
        description=(
            "## Hierarchical Task Management System\n\n"
            "Lattices provides a RESTful API for managing hierarchical tasks "
            "with infinite nesting capability.\n\n"
            "### Features\n"
            "- **Hierarchical Tasks**: Create tasks with unlimited nesting levels\n"
            "- **Tags**: Organize tasks with customizable tags\n"
            "- **Flat Fetch**: Efficient data retrieval for tree assembly\n\n"
            "### Authentication\n"
            "All endpoints (except `/health`) require a valid JWT token "
            "in the Authorization header:\n"
            "```\nAuthorization: Bearer <your_token>\n```\n\n"
            "### Rate Limits\n"
            "- GET endpoints: 30 requests/minute\n"
            "- POST/PATCH/DELETE: 10 requests/minute"
        ),
        version="1.0.0",
        debug=settings.debug,
        contact={
            "name": "Lattices Support",
        },
        license_info={
            "name": "MIT",
        },
        openapi_tags=[
            {
                "name": "health",
                "description": "Health check endpoints",
            },
            {
                "name": "todos",
                "description": "Task management operations",
            },
            {
                "name": "tags",
                "description": "Tag management operations",
            },
            {
                "name": "todo-tags",
                "description": "Task-tag relationship operations",
            },
            {
                "name": "notifications",
                "description": "Notification management operations",
            },
        ],
    )

    # Rate limiting
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Security & tracking middleware (LIFO order - last added = outermost)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIDMiddleware)

    # GZip compression for responses > 1KB
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Setup exception handlers
    setup_exception_handlers(app)

    # Include routers
    app.include_router(health_router)
    app.include_router(v1_router, prefix="/api/v1")

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=not settings.is_production,
    )
