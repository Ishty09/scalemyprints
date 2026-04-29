"""
FastAPI exception handlers.

Every error — from our own AppError subclasses to generic Exception —
gets translated into the ApiFailure envelope with a stable code and an
appropriate HTTP status.

Clients never see a raw stack trace or FastAPI's default error shape.
"""

from __future__ import annotations

import traceback

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from scalemyprints.api.schemas.envelope import failure
from scalemyprints.core.errors import AppError
from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


def _request_id(request: Request) -> str | None:
    """Pull request_id from starlette state or header."""
    return request.headers.get("X-Request-ID") or getattr(request.state, "request_id", None)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    """Translate domain AppError subclasses to ApiFailure."""
    payload = failure(
        code=exc.code,
        message=exc.message,
        details=exc.details or None,
        request_id=_request_id(request),
    )
    logger.info(
        "app_error",
        code=exc.code,
        message=exc.message,
        http_status=exc.http_status,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content=payload.model_dump(exclude_none=True),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Translate Pydantic validation errors to consistent 400 responses."""
    # Summarize the first error for `message`; put all in `details`
    errors = [
        {
            "location": list(err.get("loc", [])),
            "message": err.get("msg"),
            "type": err.get("type"),
        }
        for err in exc.errors()
    ]
    first_message = errors[0]["message"] if errors else "Validation failed"
    payload = failure(
        code="validation_error",
        message=str(first_message),
        details={"errors": errors},
        request_id=_request_id(request),
    )
    logger.info("validation_error", path=request.url.path, error_count=len(errors))
    return JSONResponse(status_code=400, content=payload.model_dump(exclude_none=True))


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """
    Translate HTTPException (raised by FastAPI or middleware, e.g., auth).
    """
    # Map common status codes to our error codes
    code_by_status = {
        400: "invalid_input",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        503: "service_unavailable",
    }
    code = code_by_status.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"

    payload = failure(code=code, message=message, request_id=_request_id(request))
    return JSONResponse(
        status_code=exc.status_code,
        content=payload.model_dump(exclude_none=True),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Last-resort handler for bugs.

    Never leak stack traces. Log with full trace for debugging.
    """
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        path=request.url.path,
        traceback=traceback.format_exc(),
    )
    payload = failure(
        code="internal_error",
        message="Something went wrong. Please try again.",
        request_id=_request_id(request),
    )
    return JSONResponse(status_code=500, content=payload.model_dump(exclude_none=True))


def register_exception_handlers(app: FastAPI) -> None:
    """Wire all handlers into the FastAPI app. Call once during app setup."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
