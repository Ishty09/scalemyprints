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
    HotMoversResponse,
    ReverseImageMatchItem,
    ReverseImageResponse,
    SpyListingItem,
    SpySearchBody,
    SpySearchResponse,
)
from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import bind_request_context, get_logger
from scalemyprints.domain.spy.enums import SpyFailureReason
from scalemyprints.domain.spy.models import SpyQuery
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
