"""
Spy public API router.

Authentication: API key (`Authorization: Bearer smp_<token>`) instead
of Supabase JWT. Powers programmatic access for users who created an
API key via the dashboard.

Surface (read-only mirror of the most useful Spy queries):
  GET  /api/v1/spy/public/feed
  POST /api/v1/spy/public/search
  POST /api/v1/spy/public/tm-overlay
  GET  /api/v1/spy/public/viral-feed

Rate-limited per-key with the same RateLimiter the JWT routes use.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from scalemyprints.api.deps import get_service_container
from scalemyprints.api.middleware.api_key_auth import get_api_key_user
from scalemyprints.api.middleware.auth import CurrentUser
from scalemyprints.api.middleware.rate_limit import RateLimiter, get_rate_limiter
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.api.schemas.spy import (
    HotMoversResponse,
    SpySearchBody,
    SpySearchResponse,
    TMOverlayBody,
    TMOverlayResponse,
    ViralFeedResponse,
    ViralSignalItem,
)
from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import bind_request_context, get_logger
from scalemyprints.domain.spy.models import SpyQuery
from scalemyprints.infrastructure.container import ServiceContainer  # noqa: TC001

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/spy/public", tags=["spy-public"])


# ---------------------------------------------------------------------------
# GET /feed
# ---------------------------------------------------------------------------


@router.get("/feed", response_model=ApiSuccess[HotMoversResponse])
async def public_hot_movers(
    user: Annotated[CurrentUser, Depends(get_api_key_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ApiSuccess[HotMoversResponse]:
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"apikey:{user.id}:feed",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )
    items = await container.spy_hot_movers_provider.recent(limit=limit)
    return success(HotMoversResponse(items=items, total=len(items)))


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post("/search", response_model=ApiSuccess[SpySearchResponse])
async def public_search(
    payload: SpySearchBody,
    user: Annotated[CurrentUser, Depends(get_api_key_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[SpySearchResponse]:
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"apikey:{user.id}:search",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )
    query = SpyQuery(
        text=payload.text,
        listing_url=payload.listing_url,
        marketplaces=payload.marketplaces,
        limit=payload.limit,
    )
    result = await container.spy_search_service.run(query)
    return success(SpySearchResponse.from_domain(result))


# ---------------------------------------------------------------------------
# POST /tm-overlay
# ---------------------------------------------------------------------------


@router.post("/tm-overlay", response_model=ApiSuccess[TMOverlayResponse])
async def public_tm_overlay(
    payload: TMOverlayBody,
    user: Annotated[CurrentUser, Depends(get_api_key_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[TMOverlayResponse]:
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"apikey:{user.id}:tm_overlay",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )
    overlay = await container.spy_tm_overlay_service.overlay(
        phrase=payload.phrase,
        marketplaces=payload.marketplaces,
        nice_classes=payload.nice_classes,
    )
    return success(
        TMOverlayResponse(
            phrase=overlay.phrase,
            opportunity_score=overlay.opportunity_score,
            risk_score=overlay.risk_score,
            saturation_score=overlay.saturation_score,
            combined_verdict=overlay.combined_verdict,
            listings_count=overlay.listings_count,
            est_monthly_gmv_usd=overlay.est_monthly_gmv_usd,
            trademark=overlay.trademark,
            duration_ms=overlay.duration_ms,
        )
    )


# ---------------------------------------------------------------------------
# GET /viral-feed
# ---------------------------------------------------------------------------


@router.get("/viral-feed", response_model=ApiSuccess[ViralFeedResponse])
async def public_viral_feed(
    user: Annotated[CurrentUser, Depends(get_api_key_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    min_pod_readiness: Annotated[int, Query(ge=0, le=100)] = 50,
    classify: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> ApiSuccess[ViralFeedResponse]:
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"apikey:{user.id}:viral_feed",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )
    result = await container.spy_viral_mining_service.run(
        per_source_limit=30,
        total_limit=limit,
        min_pod_readiness=min_pod_readiness,
        classify=classify,
    )
    return success(
        ViralFeedResponse(
            signals=[
                ViralSignalItem(
                    source=s.source.value,
                    source_url=s.source_url,
                    phrase=s.phrase,
                    detected_at=s.detected_at,
                    engagement=s.engagement,
                    momentum_score=s.momentum_score,
                    pod_readiness_score=s.pod_readiness_score,
                    existing_pod_count=s.existing_pod_count,
                    suggested_styles=s.suggested_styles,
                    note=s.note,
                )
                for s in result.signals
            ],
            sources_used=result.sources_used,
            sources_failed=[
                {"source": src, "error": err} for src, err in result.sources_failed
            ],
            total=len(result.signals),
            duration_ms=result.duration_ms,
        )
    )
