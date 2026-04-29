"""
Niche Radar API routes.

Endpoints:
- POST /api/v1/niche/search        — analyze a single niche
- GET  /api/v1/niche/events         — upcoming events for a country
- POST /api/v1/niche/expand         — LLM sub-niche generation
- GET  /api/v1/niche/trending       — pre-curated trending niches (Phase 2)

All endpoints support anonymous calls (Chrome extension free tier) but
apply tighter rate limits when unauthenticated.
"""

from __future__ import annotations

from datetime import date as date_type
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from scalemyprints.api.deps import (
    get_niche_search_service,
)
from scalemyprints.api.middleware.auth import (
    CurrentUser,
    get_current_user_or_anonymous,
)
from scalemyprints.api.middleware.rate_limit import (
    RateLimiter,
    get_rate_limiter,
)
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.api.schemas.niche import (
    EventListItem,
    NicheExpansionRequest,
    NicheExpansionResponse,
    NicheSearchRequest,
)
from scalemyprints.core.config import Settings, get_settings
from scalemyprints.core.errors import RateLimitedError
from scalemyprints.core.logging import bind_request_context, get_logger
from scalemyprints.domain.niche.enums import Country, EventCategory
from scalemyprints.domain.niche.models import NicheRecord
from scalemyprints.domain.niche.search_service import NicheSearchService
from scalemyprints.infrastructure.container import get_container

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/niche", tags=["niche"])


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _rate_limit_key(user: CurrentUser, request: Request) -> str:
    """Per-user when authenticated; per-IP when anonymous."""
    if not user.is_anonymous:
        return f"user:{user.id}"
    client_ip = (request.client.host if request.client else "unknown")
    return f"anon-niche:{client_ip}"


# -----------------------------------------------------------------------------
# POST /search
# -----------------------------------------------------------------------------


@router.post("/search", response_model=ApiSuccess[NicheRecord])
async def search_niche(
    payload: NicheSearchRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user_or_anonymous)],
    service: Annotated[NicheSearchService, Depends(get_niche_search_service)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[NicheRecord]:
    """Analyze a niche keyword across all signals."""
    settings = get_settings()
    bind_request_context(
        user_id=user.id, anonymous=user.is_anonymous, niche_keyword=payload.keyword
    )
    logger.info(
        "niche_search_request", phrase=payload.keyword, country=payload.country.value
    )

    key = _rate_limit_key(user, request)
    if user.is_anonymous:
        await limiter.check(
            key=key,
            limit=settings.rate_limit_trademark_free_tier,
            window_seconds=60 * 60 * 24,
        )
    else:
        await limiter.check(
            key=key, limit=settings.rate_limit_per_minute, window_seconds=60
        )

    record = await service.analyze(payload.keyword, payload.country)
    return success(record)


# -----------------------------------------------------------------------------
# GET /events
# -----------------------------------------------------------------------------


@router.get("/events", response_model=ApiSuccess[list[EventListItem]])
async def list_events(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user_or_anonymous)],
    country: Annotated[Country, Query()] = Country.US,
    from_date: Annotated[date_type | None, Query(alias="from")] = None,
    to_date: Annotated[date_type | None, Query(alias="to")] = None,
    category: Annotated[EventCategory | None, Query()] = None,
) -> ApiSuccess[list[EventListItem]]:
    """
    List events for a country between [from, to].

    Defaults: today → today+90 days. No rate limit (read-only, in-memory).
    """
    bind_request_context(user_id=user.id, anonymous=user.is_anonymous)

    today = datetime.now(timezone.utc).date()
    start = from_date or today
    end = to_date or (today + timedelta(days=90))

    if end < start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="'to' date must be on or after 'from' date",
        )
    if (end - start).days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 365 days",
        )

    container = get_container()
    events_provider = container.niche_events_provider
    events = await events_provider.list_events(country, start, end)

    if category:
        events = [e for e in events if e.category == category]

    items = [
        EventListItem(
            id=e.id,
            country=e.country,
            event_date=e.event_date,
            name=e.name,
            category=e.category,
            pod_relevance_score=e.pod_relevance_score,
            suggested_niches=e.suggested_niches,
            days_until=(e.event_date - today).days,
        )
        for e in events
    ]

    logger.info("events_list", count=len(items), country=country.value)
    return success(items)


# -----------------------------------------------------------------------------
# POST /expand (LLM)
# -----------------------------------------------------------------------------


@router.post("/expand", response_model=ApiSuccess[NicheExpansionResponse])
async def expand_niche(
    payload: NicheExpansionRequest,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user_or_anonymous)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[NicheExpansionResponse]:
    """Generate sub-niche suggestions via LLM."""
    bind_request_context(user_id=user.id, anonymous=user.is_anonymous)

    key = _rate_limit_key(user, request) + ":expand"
    # Tighter limit on LLM calls (cost control)
    if user.is_anonymous:
        await limiter.check(key=key, limit=3, window_seconds=60 * 60 * 24)
    else:
        await limiter.check(key=key, limit=20, window_seconds=60 * 60)

    container = get_container()
    expander = container.niche_expander
    if expander is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Niche expansion (LLM) is currently disabled",
        )

    result = await expander.expand(
        seed_keyword=payload.seed_keyword,
        country=payload.country,
        max_suggestions=payload.max_suggestions,
    )

    if result.error:
        logger.warning("niche_expand_provider_error", error=result.error)
        if result.error == "no_api_key":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Niche expansion is currently unavailable",
            )

    logger.info(
        "niche_expand_complete",
        seed=payload.seed_keyword,
        suggestion_count=len(result.suggestions),
    )

    return success(
        NicheExpansionResponse(
            seed_keyword=payload.seed_keyword,
            country=payload.country,
            suggestions=result.suggestions,
            rationale=result.rationale,
            duration_ms=result.duration_ms,
        )
    )
