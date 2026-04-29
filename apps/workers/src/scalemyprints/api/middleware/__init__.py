"""
HTTP middleware.

Cross-cutting concerns applied to every request:
- Request ID injection (for tracing)
- Structured access logging with duration
- Error boundary (catch-all for unhandled exceptions)
- Rate limiting (applied selectively per route)
"""

from scalemyprints.api.middleware.auth import CurrentUser, get_current_user
from scalemyprints.api.middleware.rate_limit import RateLimiter, get_rate_limiter
from scalemyprints.api.middleware.request_context import RequestContextMiddleware

__all__ = [
    "CurrentUser",
    "RateLimiter",
    "RequestContextMiddleware",
    "get_current_user",
    "get_rate_limiter",
]
