"""Exception handlers for the FastAPI application."""

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.config import settings
from core.exceptions import AppException, ErrorCode

logger = structlog.get_logger()


def setup_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        """Handle custom application exceptions."""
        logger.warning(
            "app_exception",
            error_code=exc.error_code.value,
            message=exc.message,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code.value,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions from FastAPI/Starlette."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": "HTTP_ERROR",
                "message": exc.detail,
                "details": None,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        logger.info("validation_error", errors=exc.errors())
        return JSONResponse(
            status_code=422,
            content={
                "error_code": ErrorCode.VALIDATION_ERROR.value,
                "message": "Request validation failed",
                "details": [
                    {
                        "field": ".".join(str(x) for x in error["loc"]),
                        "message": error["msg"],
                        "type": error["type"],
                    }
                    for error in exc.errors()
                ],
            },
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.error(
            "unhandled_exception",
            error=str(exc),
            error_type=type(exc).__name__,
            request_id=request_id,
            exc_info=True,
        )

        message = "An unexpected error occurred"
        if not settings.is_production:
            message = str(exc)

        return JSONResponse(
            status_code=500,
            content={
                "error_code": ErrorCode.INTERNAL_ERROR.value,
                "message": message,
                "details": {"request_id": request_id},
            },
        )
