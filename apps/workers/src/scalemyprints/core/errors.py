"""
Typed exception hierarchy.

Mirrors packages/contracts/src/errors.ts so errors cross the TS↔Python
boundary with consistent codes and HTTP statuses.

Design:
- All app errors inherit from AppError
- Each error has a stable `code` string (matches ERROR_CODES in TS)
- `http_status` is used by the FastAPI exception handler
- `details` is an optional dict serialized into the API response
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all application errors."""

    code: str = "internal_error"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a dict suitable for API responses."""
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


# -----------------------------------------------------------------------------
# Auth & access
# -----------------------------------------------------------------------------


class UnauthorizedError(AppError):
    code = "unauthorized"
    http_status = 401

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message)


class ForbiddenError(AppError):
    code = "forbidden"
    http_status = 403

    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(message)


class SessionExpiredError(AppError):
    code = "session_expired"
    http_status = 401

    def __init__(self, message: str = "Session expired; please log in again") -> None:
        super().__init__(message)


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------


class ValidationError(AppError):
    code = "validation_error"
    http_status = 400


class InvalidInputError(AppError):
    code = "invalid_input"
    http_status = 400


# -----------------------------------------------------------------------------
# Resources
# -----------------------------------------------------------------------------


class NotFoundError(AppError):
    code = "not_found"
    http_status = 404

    def __init__(self, resource: str) -> None:
        super().__init__(f"{resource} not found")


class AlreadyExistsError(AppError):
    code = "already_exists"
    http_status = 409


class ConflictError(AppError):
    code = "conflict"
    http_status = 409


# -----------------------------------------------------------------------------
# Limits & quotas
# -----------------------------------------------------------------------------


class QuotaExceededError(AppError):
    """
    Quota exceeded. Returns HTTP 402 (Payment Required) to signal
    that the user should upgrade.
    """

    code = "quota_exceeded"
    http_status = 402

    def __init__(self, tool: str, limit_key: str) -> None:
        super().__init__(
            f"Quota exceeded for {tool} ({limit_key}). Upgrade to continue.",
            details={"tool": tool, "limit_key": limit_key},
        )


class RateLimitedError(AppError):
    code = "rate_limited"
    http_status = 429

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        super().__init__(
            "Too many requests. Please slow down.",
            details={"retry_after_seconds": retry_after_seconds} if retry_after_seconds else {},
        )


class PlanRequiredError(AppError):
    code = "plan_required"
    http_status = 402

    def __init__(self, required_plan: str) -> None:
        super().__init__(
            f"This feature requires the {required_plan} plan or higher.",
            details={"required_plan": required_plan},
        )


# -----------------------------------------------------------------------------
# External services
# -----------------------------------------------------------------------------


class ExternalServiceError(AppError):
    code = "external_service_error"
    http_status = 502

    def __init__(self, service: str, message: str) -> None:
        super().__init__(f"{service} error: {message}", details={"service": service})


class ExternalServiceTimeoutError(AppError):
    code = "external_service_timeout"
    http_status = 504

    def __init__(self, service: str) -> None:
        super().__init__(f"{service} timed out", details={"service": service})


# -----------------------------------------------------------------------------
# Server
# -----------------------------------------------------------------------------


class ServiceUnavailableError(AppError):
    code = "service_unavailable"
    http_status = 503


class FeatureDisabledError(AppError):
    code = "feature_disabled"
    http_status = 403

    def __init__(self, feature: str) -> None:
        super().__init__(
            f"Feature '{feature}' is currently disabled.",
            details={"feature": feature},
        )


__all__ = [
    "AlreadyExistsError",
    "AppError",
    "ConflictError",
    "ExternalServiceError",
    "ExternalServiceTimeoutError",
    "FeatureDisabledError",
    "ForbiddenError",
    "InvalidInputError",
    "NotFoundError",
    "PlanRequiredError",
    "QuotaExceededError",
    "RateLimitedError",
    "ServiceUnavailableError",
    "SessionExpiredError",
    "UnauthorizedError",
    "ValidationError",
]
