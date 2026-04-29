"""
Request context middleware.

Every request gets:
- A request_id header (echoed in response)
- Structured access log line with duration + status
- structlog contextvars bound so every log line in the handler has request_id
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from scalemyprints.core.logging import bind_request_context, clear_request_context, get_logger

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Inject request_id and emit access logs.

    If the client sends X-Request-ID, we honor it. Otherwise we generate
    a UUID4. The same ID goes out in the response headers and into every
    log line via structlog contextvars.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER)
        request_id = incoming or f"req_{uuid.uuid4().hex[:16]}"

        bind_request_context(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        started_at = time.perf_counter()
        status_code = 500  # default if we crash before setting it

        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            logger.info(
                "http_request",
                status_code=status_code,
                duration_ms=duration_ms,
                client=request.client.host if request.client else None,
            )
            clear_request_context()
