"""
API response envelope.

Every response (success or failure) wraps data in a consistent shape so
clients can switch on `ok` and narrow types:

    { "ok": true, "data": {...}, "meta": {...} }
    { "ok": false, "error": { "code": "...", "message": "...", "details": {...} } }

Mirrors packages/contracts/src/api.ts — changes here must be synced there.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PaginationMeta(BaseModel):
    model_config = ConfigDict(frozen=True)

    page: int = Field(ge=1)
    per_page: int = Field(ge=1)
    total: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_prev: bool


class ApiMeta(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    pagination: PaginationMeta | None = None
    cached: bool | None = None
    cache_age_seconds: int | None = Field(default=None, ge=0)


class ApiError(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    details: dict[str, Any] | None = None
    request_id: str | None = None


class ApiSuccess(BaseModel, Generic[T]):
    """Success branch of ApiResponse<T>."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: Literal[True] = True
    data: T
    meta: ApiMeta | None = None


class ApiFailure(BaseModel):
    """Failure branch of ApiResponse<T>."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ok: Literal[False] = False
    error: ApiError


# Exported union type for route return annotations
ApiResponse = ApiSuccess[T] | ApiFailure


# -----------------------------------------------------------------------------
# Builder helpers — prefer these over constructing envelopes by hand
# -----------------------------------------------------------------------------


def success(data: T, meta: ApiMeta | None = None) -> ApiSuccess[T]:
    """Build a success envelope."""
    return ApiSuccess[T](data=data, meta=meta)


def failure(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> ApiFailure:
    """Build a failure envelope."""
    return ApiFailure(
        error=ApiError(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
        )
    )
