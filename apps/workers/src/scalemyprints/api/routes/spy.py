"""
Spy — API routes.

POST   /api/v1/spy/search          — multi-marketplace search (text or URL)
POST   /api/v1/spy/reverse-image   — upload image, return cross-platform matches
GET    /api/v1/spy/feed            — hot movers feed
GET    /api/v1/spy/listing/{id}    — fetch one listing by spy_listings.id

All endpoints require authentication. Anonymous extension calls will
use a separate set of constrained routes in Phase 3.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)

from scalemyprints.api.deps import get_service_container
from scalemyprints.api.middleware.auth import CurrentUser, get_current_user
from scalemyprints.api.middleware.rate_limit import RateLimiter, get_rate_limiter
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.api.schemas.spy import (
    AdLibraryResponse,
    AdSpyHitItem,
    HotMoversResponse,
    MinedTagItem,
    ProfitBody,
    ProfitResponse,
    ReverseImageMatchItem,
    ReverseImageResponse,
    SaturationBody,
    SaturationResponse,
    ShopAuditBody,
    ShopAuditResponse,
    ShopProfileItem,
    SpyListingItem,
    SpySearchBody,
    SpySearchResponse,
    TagFrequencyItem,
    TagMineBody,
    TagMineResponse,
    TMOverlayBody,
    TMOverlayResponse,
    VelocityRefreshBody,
    VelocityRefreshResponse,
    ViralFeedResponse,
    ViralSignalItem,
)
from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import bind_request_context, get_logger
from scalemyprints.domain.spy import profit_service, saturation_service
from scalemyprints.domain.spy.enums import (
    ShopAuditDepth,
    SpyFailureReason,
)
from scalemyprints.domain.spy.models import SpyQuery
from scalemyprints.domain.spy.profit_service import ProfitInput
from scalemyprints.infrastructure.container import ServiceContainer  # noqa: TC001

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/spy", tags=["spy"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# POST /search
# ---------------------------------------------------------------------------


@router.post(
    "/search",
    response_model=ApiSuccess[SpySearchResponse],
)
async def spy_search(
    payload: SpySearchBody,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[SpySearchResponse]:
    """Run a Spy search across selected marketplaces."""
    settings = get_settings()
    bind_request_context(user_id=user.id)
    logger.info(
        "spy_search_request",
        text=payload.text,
        url=str(payload.listing_url) if payload.listing_url else None,
        marketplaces=[m.value for m in payload.marketplaces],
        limit=payload.limit,
    )

    await limiter.check(
        key=f"user:{user.id}:spy",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    query = SpyQuery(
        text=payload.text,
        listing_url=payload.listing_url,
        marketplaces=payload.marketplaces,
        limit=payload.limit,
    )
    service = container.spy_search_service
    result = await service.run(query)

    return success(SpySearchResponse.from_domain(result))


# ---------------------------------------------------------------------------
# POST /reverse-image  (multipart upload)
# ---------------------------------------------------------------------------


@router.post(
    "/reverse-image",
    response_model=ApiSuccess[ReverseImageResponse],
)
async def spy_reverse_image(
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    file: Annotated[UploadFile, File(...)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    min_clip_cosine: Annotated[float, Query(ge=0.5, le=1.0)] = 0.70,
) -> ApiSuccess[ReverseImageResponse]:
    """Find cross-marketplace listings using the same / similar design."""
    settings = get_settings()
    bind_request_context(user_id=user.id)
    logger.info(
        "spy_reverse_image_request",
        filename=file.filename,
        content_type=file.content_type,
    )

    await limiter.check(
        key=f"user:{user.id}:spy",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_image", "message": "Empty image upload"},
        )
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"code": "image_too_large", "message": "Image exceeds 20MB"},
        )

    service = container.spy_reverse_image_service
    result = await service.search(
        image_bytes,
        limit=limit,
        min_clip_cosine=min_clip_cosine,
    )

    if result.failure_reason == SpyFailureReason.IMAGE_INVALID:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_image", "message": result.error or "Invalid image"},
        )
    if result.failure_reason == SpyFailureReason.EMBEDDING_FAILED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "embedding_unavailable",
                "message": "Image embedding service temporarily unavailable",
            },
        )

    return success(
        ReverseImageResponse(
            query_sha256=result.query_sha256,
            matches=[ReverseImageMatchItem.from_domain(m) for m in result.matches],
            total=len(result.matches),
            duration_ms=result.duration_ms,
            error=result.error,
        )
    )


# ---------------------------------------------------------------------------
# GET /feed (hot movers)
# ---------------------------------------------------------------------------


@router.get(
    "/feed",
    response_model=ApiSuccess[HotMoversResponse],
)
async def spy_hot_movers(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
) -> ApiSuccess[HotMoversResponse]:
    """Return the latest hot-mover listings."""
    bind_request_context(user_id=user.id)
    items = await container.spy_hot_movers_provider.recent(limit=limit)
    return success(HotMoversResponse(items=items, total=len(items)))


# ---------------------------------------------------------------------------
# GET /listing/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/listing/{listing_id}",
    response_model=ApiSuccess[SpyListingItem],
)
async def spy_get_listing(
    listing_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[SpyListingItem]:
    """Fetch a tracked listing by id."""
    bind_request_context(user_id=user.id)
    listing = await container.spy_listing_store.get_listing(listing_id)
    if listing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Listing not found"},
        )
    return success(SpyListingItem.from_domain(listing))


# ---------------------------------------------------------------------------
# POST /shop-audit
# ---------------------------------------------------------------------------


@router.post(
    "/shop-audit",
    response_model=ApiSuccess[ShopAuditResponse],
)
async def spy_shop_audit(
    payload: ShopAuditBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[ShopAuditResponse]:
    """Run a forensic teardown on a shop."""
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"user:{user.id}:spy:shop_audit",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    service = container.spy_shop_audit_service
    depth = ShopAuditDepth(payload.depth)
    report = await service.audit(payload.marketplace, payload.handle, depth=depth)

    shop_item = ShopProfileItem(
        marketplace=report.shop.marketplace,
        handle=report.shop.handle,
        display_name=report.shop.display_name,
        url=report.shop.url,
        location=report.shop.location,
        total_sales=report.shop.total_sales,
        listings_count=report.shop.listings_count,
        avg_review_rating=report.shop.avg_review_rating,
        reviews_count=report.shop.reviews_count,
        last_seen_at=report.shop.last_seen_at,
    )
    return success(
        ShopAuditResponse(
            shop=shop_item,
            depth=report.depth.value,
            listings_sampled=report.listings_sampled,
            est_monthly_revenue_usd=report.est_monthly_revenue_usd,
            avg_price_usd=report.avg_price_usd,
            new_listings_last_30d=report.new_listings_last_30d,
            restock_cadence_days=report.restock_cadence_days,
            top_listings=[SpyListingItem.from_domain(l) for l in report.top_listings],
            most_used_tags=[
                TagFrequencyItem(tag=t, count=c) for t, c in report.most_used_tags
            ],
            captured_at=report.captured_at,
            error=report.error,
        )
    )


# ---------------------------------------------------------------------------
# POST /saturation
# ---------------------------------------------------------------------------


@router.post(
    "/saturation",
    response_model=ApiSuccess[SaturationResponse],
)
async def spy_saturation(
    payload: SaturationBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[SaturationResponse]:
    """Compute saturation/difficulty for a phrase or a set of listings."""
    bind_request_context(user_id=user.id)

    listings = []

    # Resolve via stored listing IDs first
    for lid in payload.listing_ids[:200]:
        row = await container.spy_listing_store.get_listing(lid)
        if row is not None:
            listings.append(row)

    # Optionally augment via live search
    if payload.use_live_search and payload.phrase:
        query = SpyQuery(
            text=payload.phrase,
            marketplaces=payload.marketplaces,
            limit=50,
        )
        result = await container.spy_search_service.run(query)
        listings.extend(result.listings)

    score = saturation_service.compute(listings, phrase=payload.phrase)
    return success(
        SaturationResponse(
            score=score.score,
            saturation_class=score.saturation_class.value,
            listings_count=score.listings_count,
            unique_shops=score.unique_shops,
            hhi=score.hhi,
            gmv_pool_usd=score.gmv_pool_usd,
            density_component=score.density_component,
            concentration_component=score.concentration_component,
            velocity_component=score.velocity_component,
            recency_component=score.recency_component,
            explanation=score.explanation,
        )
    )


# ---------------------------------------------------------------------------
# POST /profit
# ---------------------------------------------------------------------------


@router.post(
    "/profit",
    response_model=ApiSuccess[ProfitResponse],
)
async def spy_profit(
    payload: ProfitBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiSuccess[ProfitResponse]:
    """Per-unit profit math for a POD listing."""
    bind_request_context(user_id=user.id)
    breakdown = profit_service.compute(
        ProfitInput(
            marketplace=payload.marketplace,
            product_type=payload.product_type,  # type: ignore[arg-type]
            sale_price_usd=payload.sale_price_usd,
            printer=payload.printer,  # type: ignore[arg-type]
            shipping_usd=payload.shipping_usd,
            ad_cpc_usd=payload.ad_cpc_usd,
            ad_conversion_rate=payload.ad_conversion_rate,
        )
    )
    return success(
        ProfitResponse(
            sale_price_usd=breakdown.sale_price_usd,
            base_cost_usd=breakdown.base_cost_usd,
            marketplace_fee_usd=breakdown.marketplace_fee_usd,
            shipping_usd=breakdown.shipping_usd,
            ad_cost_usd=breakdown.ad_cost_usd,
            profit_usd=breakdown.profit_usd,
            margin_pct=breakdown.margin_pct,
            printer=breakdown.printer,
            note=breakdown.note,
        )
    )


# ---------------------------------------------------------------------------
# GET /ads
# ---------------------------------------------------------------------------


@router.get(
    "/ads",
    response_model=ApiSuccess[AdLibraryResponse],
)
async def spy_ads(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    keyword: Annotated[str | None, Query(max_length=200)] = None,
    page_handle: Annotated[str | None, Query(max_length=120)] = None,
    country: Annotated[str, Query(max_length=10)] = "ALL",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ApiSuccess[AdLibraryResponse]:
    """Search the Facebook ad library for matching ads."""
    bind_request_context(user_id=user.id)
    adapter = container.spy_fb_ad_library
    result = await adapter.search(
        keyword=keyword,
        page_handle=page_handle,
        country=country,
        limit=limit,
    )
    return success(
        AdLibraryResponse(
            platform=result.platform.value,
            hits=[
                AdSpyHitItem(
                    platform=h.platform.value,
                    ad_id=h.ad_id,
                    page_or_handle=h.page_or_handle,
                    page_id=h.page_id,
                    primary_text=h.primary_text,
                    cta=h.cta,
                    landing_url=h.landing_url,
                    started_at=h.started_at,
                    last_seen_at=h.last_seen_at,
                    impressions_lower=h.impressions_lower,
                    impressions_upper=h.impressions_upper,
                    countries=h.countries,
                )
                for h in result.hits
            ],
            total=len(result.hits),
            duration_ms=result.duration_ms,
            error=result.error,
        )
    )


# ---------------------------------------------------------------------------
# POST /_internal/refresh-velocity  (cron-only, secured by header)
# ---------------------------------------------------------------------------


@router.post(
    "/_internal/refresh-velocity",
    response_model=ApiSuccess[VelocityRefreshResponse],
)
async def spy_refresh_velocity(
    payload: VelocityRefreshBody,
    request: Request,
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[VelocityRefreshResponse]:
    """
    Internal velocity refresh — invoked by Cloudflare cron / external
    scheduler. Auth is via the `X-Internal-Secret` header (NOT user JWT).
    """
    settings = get_settings()
    secret = settings.internal_api_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "internal_secret_not_configured", "message": "cron disabled"},
        )
    provided = request.headers.get("x-internal-secret", "")
    if provided != secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "unauthorized", "message": "missing or bad internal secret"},
        )

    candidates = await container.spy_listing_store.candidates_for_refresh(
        limit=payload.limit,
        max_age_hours=payload.max_age_hours,
    )
    service = container.spy_velocity_refresh_service
    summary = await service.refresh(candidates)
    return success(
        VelocityRefreshResponse(
            started_at=summary.started_at,
            completed_at=summary.completed_at,
            duration_ms=summary.duration_ms,
            candidates=summary.candidates,
            refreshed=summary.refreshed,
            failed=summary.failed,
            spikes_detected=summary.spikes_detected,
            by_marketplace=summary.by_marketplace,
            errors=summary.errors,
        )
    )


# ---------------------------------------------------------------------------
# GET /viral-feed
# ---------------------------------------------------------------------------


@router.get(
    "/viral-feed",
    response_model=ApiSuccess[ViralFeedResponse],
)
async def spy_viral_feed(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    min_pod_readiness: Annotated[int, Query(ge=0, le=100)] = 50,
    classify: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=200)] = 60,
) -> ApiSuccess[ViralFeedResponse]:
    """Live viral-mining feed: Reddit + TikTok + Twitter trending, scored by POD readiness."""
    bind_request_context(user_id=user.id)
    service = container.spy_viral_mining_service
    result = await service.run(
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


# ---------------------------------------------------------------------------
# POST /tag-mine
# ---------------------------------------------------------------------------


@router.post(
    "/tag-mine",
    response_model=ApiSuccess[TagMineResponse],
)
async def spy_tag_mine(
    payload: TagMineBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[TagMineResponse]:
    """Cross-marketplace tag harvester."""
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"user:{user.id}:spy:tag_mine",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    service = container.spy_tag_mining_service
    result = await service.mine(
        seed=payload.seed,
        marketplaces=payload.marketplaces,
        per_marketplace_limit=payload.per_marketplace_limit,
        top_n=payload.top_n,
    )
    return success(
        TagMineResponse(
            seed=result.seed,
            tags=[
                MinedTagItem(
                    tag=t.tag,
                    total_count=t.total_count,
                    by_marketplace=t.by_marketplace,
                    distinct_marketplaces=t.distinct_marketplaces,
                    sample_listings=t.sample_listings,
                )
                for t in result.tags
            ],
            total_listings_scanned=result.total_listings_scanned,
            duration_ms=result.duration_ms,
        )
    )


# ---------------------------------------------------------------------------
# POST /tm-overlay
# ---------------------------------------------------------------------------


@router.post(
    "/tm-overlay",
    response_model=ApiSuccess[TMOverlayResponse],
)
async def spy_tm_overlay(
    payload: TMOverlayBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[TMOverlayResponse]:
    """
    Fuse Spy and Trademark modules for a phrase: returns opportunity
    score + risk score + verdict for one-shot go/caution/block.
    """
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"user:{user.id}:spy:tm_overlay",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    service = container.spy_tm_overlay_service
    overlay = await service.overlay(
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
