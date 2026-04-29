"""Cross-cutting concerns: configuration, logging, error handling."""

from scalemyprints.core.config import Settings, get_settings
from scalemyprints.core.errors import (
    AppError,
    ExternalServiceError,
    ForbiddenError,
    NotFoundError,
    QuotaExceededError,
    RateLimitedError,
    UnauthorizedError,
    ValidationError,
)
from scalemyprints.core.logging import configure_logging, get_logger

__all__ = [
    "Settings",
    "get_settings",
    "configure_logging",
    "get_logger",
    "AppError",
    "UnauthorizedError",
    "ForbiddenError",
    "ValidationError",
    "NotFoundError",
    "QuotaExceededError",
    "RateLimitedError",
    "ExternalServiceError",
]
