"""
Trademark Shield API routes.

Routes are THIN — they:
1. Parse and validate input (Pydantic does this automatically)
2. Resolve the caller and enforce rate limits
3. Dispatch to the domain service
4. Wrap the response in the ApiResponse envelope

All errors bubble up to the exception handlers.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from scalemyprints.api.deps import get_trademark_search_service
from scalemyprints.api.middleware.auth import (
    CurrentUser,
    get_current_user_or_anonymous,
)
from scalemyprints.api.middleware.rate_limit import (
    RateLimiter,
    client_ip,
    get_rate_limiter,
)
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.api.schemas.trademark import (
    SearchBody,
    SearchResponse,
)
from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.models import TrademarkSearchRequest
from scalemyprints.domain.trademark.search_service import TrademarkSearchService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/trademark", tags=["trademark"])


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _rate_limit_key(user: CurrentUser, request: Request) -> str:
    """Pick a stable rate-limit key based on identity."""
    if user.is_anonymous:
        return f"anon:{client_ip(request)}"
    return f"user:{user.id}"


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------


@router.post("/search", response_model=ApiSuccess[SearchResponse])
async def search_trademark(
    body: SearchBody,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user_or_anonymous)],
    service: Annotated[TrademarkSearchService, Depends(get_trademark_search_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[SearchResponse]:
    """
    Execute a trademark risk search.

    Supports both authenticated users (dashboard) and anonymous callers
    (Chrome extension free tier). Anonymous callers get a stricter rate
    limit.
    """
    settings = get_settings()
    key = _rate_limit_key(user, request)

    # Anonymous: 5 per minute (matches free tier)
    # Authenticated: fall through to general limit (60 per minute default)
    if user.is_anonymous:
        await limiter.check(
            key=key,
            limit=settings.rate_limit_trademark_free_tier,
            window_seconds=60,
        )
    else:
        await limiter.check(
            key=key,
            limit=settings.rate_limit_per_minute,
            window_seconds=60,
        )

    # Translate API body to domain request
    domain_request = TrademarkSearchRequest(
        phrase=body.phrase,
        jurisdictions=body.jurisdictions,
        nice_classes=body.nice_classes,
        check_common_law=body.check_common_law,
    )

    logger.info(
        "trademark_search_request",
        user_id=user.id,
        anonymous=user.is_anonymous,
        phrase=body.phrase,
    )

    response = await service.search(domain_request)
    return success(response)
