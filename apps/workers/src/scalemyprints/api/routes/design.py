"""
Design Engine — API routes.

Endpoints:
  POST   /api/v1/design/generate         — submit a new design (auth req)
  GET    /api/v1/design/jobs/{job_id}    — fetch single job
  GET    /api/v1/design/jobs             — list user's jobs (paginated)
  POST   /api/v1/design/jobs/{job_id}/iterate — refine an existing design
  DELETE /api/v1/design/jobs/{job_id}    — soft-delete a job
  GET    /api/v1/design/quota            — current plan + remaining
  GET    /api/v1/design/styles           — list available style presets

All endpoints require authentication. The Chrome extension should NOT
submit designs (no anonymous tier here — image gen costs real money).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from scalemyprints.api.deps import get_service_container
from scalemyprints.api.middleware.auth import CurrentUser, get_current_user
from scalemyprints.api.middleware.rate_limit import RateLimiter, get_rate_limiter
from scalemyprints.api.schemas.design import (
    DesignGenerateBody,
    DesignJobListItem,
    DesignJobListResponse,
    DesignJobResponse,
    QuotaResponse,
    StylePresetItem,
)
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import bind_request_context, get_logger
from scalemyprints.domain.design.enums import DesignStatus, FailureReason
from scalemyprints.domain.design.style_presets import STYLE_PRESETS
from scalemyprints.infrastructure.container import ServiceContainer  # noqa: TC001

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/design", tags=["design"])


# ---------------------------------------------------------------------------
# POST /generate
# ---------------------------------------------------------------------------


@router.post(
    "/generate",
    response_model=ApiSuccess[DesignJobResponse],
    status_code=status.HTTP_201_CREATED,
)
async def generate_design(
    payload: DesignGenerateBody,
    request: Request,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[DesignJobResponse]:
    """Generate a new design synchronously."""
    settings = get_settings()
    bind_request_context(user_id=user.id)
    logger.info(
        "design_generate_request",
        style=payload.style.value,
        aspect=payload.aspect.value,
        variant_count=payload.variant_count,
    )

    await limiter.check(
        key=f"user:{user.id}:design",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    service = container.build_design_generation_service()
    job = await service.submit(user_id=user.id, request=payload.to_request())

    if job.status == DesignStatus.FAILED:
        # Categorize failures into appropriate HTTP errors but still return
        # the full job envelope so the UI can render a useful message.
        if job.failure_reason == FailureReason.QUOTA_EXCEEDED:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "code": "quota_exceeded",
                    "message": job.failure_message or "Monthly design limit reached.",
                },
            )
        if job.failure_reason == FailureReason.POLICY_VIOLATION:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "code": "policy_violation",
                    "message": "Prompt violates the content policy.",
                },
            )
        if job.failure_reason == FailureReason.PROVIDER_RATE_LIMITED:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "provider_rate_limited",
                    "message": "Image provider is rate-limited; try again shortly.",
                },
            )
        if job.failure_reason == FailureReason.PROVIDER_UNAVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={
                    "code": "provider_unavailable",
                    "message": "Image generation is currently unavailable.",
                },
            )
        # Other failure reasons fall through and return as 200 with status=failed.

    return success(DesignJobResponse.from_domain(job))


# ---------------------------------------------------------------------------
# GET /jobs/{id}
# ---------------------------------------------------------------------------


@router.get(
    "/jobs/{job_id}",
    response_model=ApiSuccess[DesignJobResponse],
)
async def get_design_job(
    job_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[DesignJobResponse]:
    """Fetch a single job by id (must belong to caller)."""
    bind_request_context(user_id=user.id)
    job = await container.design_job_store.get(job_id, user.id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Design job not found"},
        )
    return success(DesignJobResponse.from_domain(job))


# ---------------------------------------------------------------------------
# GET /jobs
# ---------------------------------------------------------------------------


@router.get(
    "/jobs",
    response_model=ApiSuccess[DesignJobListResponse],
)
async def list_design_jobs(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    job_status: Annotated[DesignStatus | None, Query(alias="status")] = None,
) -> ApiSuccess[DesignJobListResponse]:
    """List the caller's design jobs, newest first."""
    bind_request_context(user_id=user.id)
    jobs, total = await container.design_job_store.list_for_user(
        user.id, limit=limit, offset=offset, status=job_status
    )
    return success(
        DesignJobListResponse(
            jobs=[DesignJobListItem.from_domain(j) for j in jobs],
            total=total,
            limit=limit,
            offset=offset,
        )
    )


# ---------------------------------------------------------------------------
# POST /jobs/{id}/iterate
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/iterate",
    response_model=ApiSuccess[DesignJobResponse],
    status_code=status.HTTP_201_CREATED,
)
async def iterate_design_job(
    job_id: str,
    payload: DesignGenerateBody,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
    limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
) -> ApiSuccess[DesignJobResponse]:
    """Iterate on a previous job — same flow but tagged as a child."""
    settings = get_settings()
    bind_request_context(user_id=user.id, parent_job_id=job_id)

    parent = await container.design_job_store.get(job_id, user.id)
    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Parent job not found"},
        )

    await limiter.check(
        key=f"user:{user.id}:design",
        limit=settings.rate_limit_per_minute,
        window_seconds=60,
    )

    service = container.build_design_generation_service()
    job = await service.submit(
        user_id=user.id,
        request=payload.to_request(parent_job_id=parent.id),
    )
    return success(DesignJobResponse.from_domain(job))


# ---------------------------------------------------------------------------
# DELETE /jobs/{id}
# ---------------------------------------------------------------------------


@router.delete(
    "/jobs/{job_id}",
    response_model=ApiSuccess[dict[str, object]],
)
async def delete_design_job(
    job_id: str,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[dict[str, object]]:
    """Soft-delete a design job."""
    bind_request_context(user_id=user.id)
    deleted = await container.design_job_store.soft_delete(job_id, user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "Design job not found"},
        )
    return success({"id": job_id, "deleted": True})


# ---------------------------------------------------------------------------
# GET /quota
# ---------------------------------------------------------------------------


@router.get(
    "/quota",
    response_model=ApiSuccess[QuotaResponse],
)
async def get_design_quota(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> ApiSuccess[QuotaResponse]:
    """Return the caller's current plan + remaining quota."""
    bind_request_context(user_id=user.id)
    snap = await container.design_quota.snapshot(user.id)
    return success(QuotaResponse.from_domain(snap))


# ---------------------------------------------------------------------------
# GET /styles
# ---------------------------------------------------------------------------


@router.get(
    "/styles",
    response_model=ApiSuccess[list[StylePresetItem]],
)
async def list_styles() -> ApiSuccess[list[StylePresetItem]]:
    """Return the curated style presets — drives the UI chip selector."""
    items = [
        StylePresetItem(
            id=preset.style,
            label=preset.label,
            description=preset.description,
        )
        for preset in STYLE_PRESETS.values()
    ]
    return success(items)
