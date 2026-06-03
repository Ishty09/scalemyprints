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
    AlertChannelConfigItem,
    AlertItem,
    AlertListResponse,
    ApiKeyCreateBody,
    ApiKeyCreatedResponse,
    ApiKeyItem,
    CompetitorDiffBody,
    CompetitorDiffResponse,
    HotMoversResponse,
    MinedTagItem,
    NicheSuggesterBody,
    NicheSuggesterResponse,
    NicheSuggestionItem,
    ProfitBody,
    ProfitResponse,
    ReverseImageMatchItem,
    ReverseImageResponse,
    SaturationBody,
    SaturationResponse,
    SeasonalityBody,
    SeasonalityResponse,
    SeasonalityWindowItem,
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
    DeliverAlertsBody,
    DeliverAlertsResponse,
    LivePriceQuoteItem,
    PrinterPricesResponse,
    VelocityRefreshBody,
    VelocityRefreshResponse,
    ViralFeedResponse,
    ViralSignalItem,
    WatchlistCreateBody,
    WatchlistItem,
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
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[ProfitResponse]:
    """Per-unit profit math for a POD listing."""
    bind_request_context(user_id=user.id)

    # Phase 4.8 — try the live printer-price provider before falling
    # back to the static 2026-Q2 table.
    live_quote: float | None = None
    provider = container.spy_printer_price_providers.get(payload.printer)
    if provider is not None:
        try:
            q = await provider.quote(payload.product_type)
            if not q.error and q.base_cost_usd > 0:
                live_quote = q.base_cost_usd
        except Exception as e:
            logger.warning("live_printer_quote_failed", error=str(e))

    breakdown = profit_service.compute(
        ProfitInput(
            marketplace=payload.marketplace,
            product_type=payload.product_type,  # type: ignore[arg-type]
            sale_price_usd=payload.sale_price_usd,
            printer=payload.printer,  # type: ignore[arg-type]
            shipping_usd=payload.shipping_usd,
            ad_cpc_usd=payload.ad_cpc_usd,
            ad_conversion_rate=payload.ad_conversion_rate,
        ),
        live_base_cost_usd=live_quote,
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

    # Close the alert loop — emit watchlist alerts for any spikes that
    # match a user's watchlist, then dispatch through configured channels.
    if summary.velocity_signals:
        watchlist_service = container.spy_watchlist_service
        try:
            await watchlist_service.evaluate(
                velocity_signals=summary.velocity_signals,
            )
            # Best-effort fan-out — pending alerts dispatch synchronously.
            # The store interface doesn't expose "pending list" yet, so
            # for cron we settle for evaluate(). Phase 5 adds the
            # deliver_pending loop.
        except Exception as e:  # noqa: BLE001
            logger.warning("spy_velocity_alert_evaluate_failed", error=str(e))
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


# ===========================================================================
# Phase 4 endpoints
# ===========================================================================


def _serialize_watchlist(w: object) -> WatchlistItem:
    from scalemyprints.domain.spy.watchlist_models import Watchlist  # noqa: PLC0415

    assert isinstance(w, Watchlist)
    return WatchlistItem(
        id=w.id,
        user_id=w.user_id,
        watch_type=w.watch_type.value,
        target=w.target,
        label=w.label,
        triggers=[t.value for t in w.triggers],
        channels=[
            AlertChannelConfigItem(
                channel=c.channel.value,
                target=c.target,
                enabled=c.enabled,
            )
            for c in w.channels
        ],
        enabled=w.enabled,
        created_at=w.created_at,
        updated_at=w.updated_at,
    )


@router.post("/watchlists", response_model=ApiSuccess[WatchlistItem])
async def spy_create_watchlist(
    payload: WatchlistCreateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[WatchlistItem]:
    bind_request_context(user_id=user.id)
    from scalemyprints.domain.spy.watchlist_models import (  # noqa: PLC0415
        AlertChannel,
        AlertChannelConfig,
        AlertTrigger,
        WatchType,
    )

    try:
        triggers = [AlertTrigger(t) for t in payload.triggers]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_trigger", "message": str(e)},
        ) from e

    channels = [
        AlertChannelConfig(
            channel=AlertChannel(c.channel),
            target=c.target,
            enabled=c.enabled,
        )
        for c in payload.channels
    ]
    if not channels:
        channels = [AlertChannelConfig(channel=AlertChannel.IN_APP)]

    service = container.spy_watchlist_service
    w = await service.create(
        user_id=user.id,
        watch_type=WatchType(payload.watch_type),
        target=payload.target,
        label=payload.label,
        triggers=triggers,
        channels=channels,
    )
    return success(_serialize_watchlist(w))


@router.get("/watchlists", response_model=ApiSuccess[list[WatchlistItem]])
async def spy_list_watchlists(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[list[WatchlistItem]]:
    bind_request_context(user_id=user.id)
    rows = await container.spy_watchlist_service.list_for_user(user.id)
    return success([_serialize_watchlist(r) for r in rows])


@router.delete("/watchlists/{watchlist_id}", response_model=ApiSuccess[dict[str, object]])
async def spy_delete_watchlist(
    watchlist_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[dict[str, object]]:
    bind_request_context(user_id=user.id)
    deleted = await container.spy_watchlist_service.delete(watchlist_id, user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Watchlist not found"},
        )
    return success({"id": watchlist_id, "deleted": True})


@router.get("/alerts", response_model=ApiSuccess[AlertListResponse])
async def spy_list_alerts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    only_unread: Annotated[bool, Query()] = False,
) -> ApiSuccess[AlertListResponse]:
    bind_request_context(user_id=user.id)
    rows = await container.spy_alert_store.list_for_user(
        user.id, limit=limit, only_unread=only_unread
    )
    unread = await container.spy_alert_store.list_for_user(
        user.id, limit=500, only_unread=True
    )
    return success(
        AlertListResponse(
            items=[
                AlertItem(
                    id=r.id,
                    watchlist_id=r.watchlist_id,
                    trigger=r.trigger.value,
                    status=r.status.value,
                    headline=r.headline,
                    detail=r.detail,
                    severity=r.severity,
                    channels_delivered=[c.value for c in r.channels_delivered],
                    created_at=r.created_at,
                    delivered_at=r.delivered_at,
                    read_at=r.read_at,
                )
                for r in rows
            ],
            unread_count=len(unread),
        )
    )


@router.post("/niche-suggester", response_model=ApiSuccess[NicheSuggesterResponse])
async def spy_niche_suggester(
    payload: NicheSuggesterBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[NicheSuggesterResponse]:
    settings = get_settings()
    bind_request_context(user_id=user.id)
    await limiter.check(
        key=f"user:{user.id}:spy:niche_suggester",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    from scalemyprints.domain.spy.niche_suggester_service import (  # noqa: PLC0415
        NicheSuggesterInput,
    )

    result = await container.spy_niche_suggester_service.suggest(
        NicheSuggesterInput(
            preferred_styles=payload.preferred_styles,
            excluded_phrases=payload.excluded_phrases,
            marketplaces=payload.marketplaces,
            limit=payload.limit,
            min_pod_readiness=payload.min_pod_readiness,
            max_risk=payload.max_risk,
        )
    )
    return success(
        NicheSuggesterResponse(
            suggestions=[
                NicheSuggestionItem(
                    phrase=s.phrase,
                    opportunity_score=s.opportunity_score,
                    risk_score=s.risk_score,
                    saturation_score=s.saturation_score,
                    pod_readiness_score=s.pod_readiness_score,
                    est_monthly_gmv_usd=s.est_monthly_gmv_usd,
                    suggested_styles=s.suggested_styles,
                    rationale=s.rationale,
                    source=s.source,
                    sample_urls=s.sample_urls,
                )
                for s in result.suggestions
            ],
            candidates_considered=result.candidates_considered,
            duration_ms=result.duration_ms,
        )
    )


@router.post(
    "/competitor-diff",
    response_model=ApiSuccess[CompetitorDiffResponse],
)
async def spy_competitor_diff(
    payload: CompetitorDiffBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> ApiSuccess[CompetitorDiffResponse]:
    bind_request_context(user_id=user.id)
    from scalemyprints.domain.spy.competitor_diff_service import (  # noqa: PLC0415
        compute_diff,
    )
    from scalemyprints.domain.spy.models import ShopAuditReport  # noqa: PLC0415

    try:
        previous = ShopAuditReport.model_validate(payload.previous)
        current = ShopAuditReport.model_validate(payload.current)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "invalid_audit", "message": str(e)},
        ) from e

    diff = compute_diff(previous=previous, current=current)
    return success(
        CompetitorDiffResponse(
            marketplace=diff.marketplace,
            handle=diff.handle,
            previous_at=diff.previous_at,
            current_at=diff.current_at,
            new_listings=diff.new_listings,
            removed_listings=diff.removed_listings,
            price_changes=diff.price_changes,
            restock_signals=diff.restock_signals,
            velocity_movers=diff.velocity_movers,
            note=diff.note,
        )
    )


@router.post("/seasonality", response_model=ApiSuccess[SeasonalityResponse])
async def spy_seasonality(
    payload: SeasonalityBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[SeasonalityResponse]:
    bind_request_context(user_id=user.id)
    forecast = await container.spy_seasonality_service.forecast(
        seed=payload.seed,
        horizon_days=payload.horizon_days,
        country=payload.country,
        lag_days=payload.lag_days,
    )
    return success(
        SeasonalityResponse(
            seed=forecast.seed,
            windows=[
                SeasonalityWindowItem(
                    name=w.name,
                    starts_at=w.starts_at,
                    peaks_at=w.peaks_at,
                    ends_at=w.ends_at,
                    confidence=w.confidence,
                    suggested_drop_by=w.suggested_drop_by,
                    rationale=w.rationale,
                    related_event=w.related_event,
                )
                for w in forecast.windows
            ],
            horizon_days=forecast.horizon_days,
            computed_at=forecast.computed_at,
        )
    )


@router.post("/api-keys", response_model=ApiSuccess[ApiKeyCreatedResponse])
async def spy_create_api_key(
    payload: ApiKeyCreateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[ApiKeyCreatedResponse]:
    bind_request_context(user_id=user.id)
    store = container.spy_api_key_store
    key, raw = await store.create(user_id=user.id, label=payload.label)
    return success(
        ApiKeyCreatedResponse(
            key=ApiKeyItem(
                id=key.id,
                label=key.label,
                prefix=key.prefix,
                scopes=key.scopes,
                revoked=key.revoked,
                last_used_at=key.last_used_at,
                created_at=key.created_at,
            ),
            clear_text=raw,
        )
    )


@router.get("/api-keys", response_model=ApiSuccess[list[ApiKeyItem]])
async def spy_list_api_keys(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[list[ApiKeyItem]]:
    bind_request_context(user_id=user.id)
    rows = await container.spy_api_key_store.list_for_user(user.id)
    return success(
        [
            ApiKeyItem(
                id=k.id,
                label=k.label,
                prefix=k.prefix,
                scopes=k.scopes,
                revoked=k.revoked,
                last_used_at=k.last_used_at,
                created_at=k.created_at,
            )
            for k in rows
        ]
    )


@router.delete("/api-keys/{key_id}", response_model=ApiSuccess[dict[str, object]])
async def spy_revoke_api_key(
    key_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[dict[str, object]]:
    bind_request_context(user_id=user.id)
    ok = await container.spy_api_key_store.revoke(key_id, user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "API key not found"},
        )
    return success({"id": key_id, "revoked": True})


# ---------------------------------------------------------------------------
# POST /_internal/deliver-alerts  (cron-only, secured by header)
# ---------------------------------------------------------------------------


@router.post(
    "/_internal/deliver-alerts",
    response_model=ApiSuccess[DeliverAlertsResponse],
)
async def spy_deliver_alerts(
    payload: DeliverAlertsBody,
    request: Request,
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[DeliverAlertsResponse]:
    """Pop pending alerts and dispatch them through configured channels."""
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

    result = await container.spy_watchlist_service.deliver_pending(limit=payload.limit)
    return success(
        DeliverAlertsResponse(
            attempted=result.attempted,
            delivered=result.delivered,
            failed=result.failed,
            by_channel=result.by_channel,
        )
    )


# ---------------------------------------------------------------------------
# GET /printer-prices — live quotes for one product_type
# ---------------------------------------------------------------------------


@router.get(
    "/printer-prices",
    response_model=ApiSuccess[PrinterPricesResponse],
)
async def spy_printer_prices(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    product_type: Annotated[str, Query(min_length=1, max_length=40)] = "t_shirt",
) -> ApiSuccess[PrinterPricesResponse]:
    """Live base-cost quotes for all configured printers + a single product."""
    bind_request_context(user_id=user.id)
    providers = container.spy_printer_price_providers
    quotes: list[LivePriceQuoteItem] = []
    for printer_id, provider in providers.items():
        try:
            q = await provider.quote(product_type)
        except Exception as e:
            logger.warning(
                "printer_price_route_failed",
                printer=printer_id,
                error=str(e),
            )
            continue
        quotes.append(
            LivePriceQuoteItem(
                printer=q.printer,
                product_type=q.product_type,
                base_cost_usd=q.base_cost_usd,
                currency=q.currency,
                source_url=q.source_url,
                fetched_at=q.fetched_at,
                error=q.error,
            )
        )
    return success(
        PrinterPricesResponse(product_type=product_type, quotes=quotes),
    )
