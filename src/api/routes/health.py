"""Health check endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from infrastructure.database.session import get_async_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: str
    environment: str
    database: str | None = None


@router.get("/health", response_model=HealthResponse, summary="Basic health check")
async def health_check() -> HealthResponse:
    """
    Basic health check for load balancers.

    Returns service status without checking dependencies. Fast and lightweight.
    """
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat(),
        environment=settings.app_env,
    )


@router.get(
    "/health/detailed",
    response_model=HealthResponse,
    summary="Detailed health check",
)
async def detailed_health_check(
    db: AsyncSession = Depends(get_async_session),
) -> HealthResponse:
    """
    Detailed health check including database connectivity.

    Use for monitoring dashboards that need to verify all dependencies.
    """
    db_status = "unknown"

    try:
        await db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"

    overall_status = "healthy" if db_status == "healthy" else "degraded"

    return HealthResponse(
        status=overall_status,
        version="1.0.0",
        timestamp=datetime.utcnow().isoformat(),
        environment=settings.app_env,
        database=db_status,
    )
