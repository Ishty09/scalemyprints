"""
Design Engine — request/response DTOs.

These wrap the domain DesignRequest / DesignJob models for the HTTP
boundary. Mirror packages/contracts/src/design.ts.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStatus,
    DesignStyle,
    OutputFormat,
)
from scalemyprints.domain.design.models import (
    DesignArtifact,
    DesignJob,
    DesignRequest,
    QuotaSnapshot,
)

# ---------------------------------------------------------------------------
# POST /design/generate
# ---------------------------------------------------------------------------


class DesignGenerateBody(BaseModel):
    """Body for POST /api/v1/design/generate."""

    model_config = ConfigDict(extra="forbid")

    prompt: str = Field(min_length=3, max_length=600)
    style: DesignStyle = DesignStyle.MINIMAL
    aspect: DesignAspect = DesignAspect.SQUARE
    output_format: OutputFormat = OutputFormat.PNG_TRANSPARENT
    variant_count: int = Field(default=1, ge=1, le=4)
    negative_prompt: str | None = Field(default=None, max_length=400)
    seed: int | None = Field(default=None, ge=0)

    def to_request(self, *, parent_job_id: str | None = None) -> DesignRequest:
        return DesignRequest(
            prompt=self.prompt,
            style=self.style,
            aspect=self.aspect,
            output_format=self.output_format,
            variant_count=self.variant_count,
            negative_prompt=self.negative_prompt,
            seed=self.seed,
            parent_job_id=parent_job_id,
        )


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class DesignJobResponse(BaseModel):
    """Public job shape — same as domain `DesignJob`."""

    model_config = ConfigDict(extra="forbid")

    id: str
    user_id: str
    status: DesignStatus
    request: DesignRequest
    enriched_prompt: str | None
    artifacts: list[DesignArtifact]
    failure_reason: str | None
    failure_message: str | None
    providers_attempted: list[str]
    plan_at_creation: str | None
    cost_usd_estimate: float | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    duration_ms: int
    parent_job_id: str | None
    revision: int

    @classmethod
    def from_domain(cls, job: DesignJob) -> DesignJobResponse:
        return cls(
            id=job.id,
            user_id=job.user_id,
            status=job.status,
            request=job.request,
            enriched_prompt=job.enriched_prompt,
            artifacts=job.artifacts,
            failure_reason=job.failure_reason.value if job.failure_reason else None,
            failure_message=job.failure_message,
            providers_attempted=job.providers_attempted,
            plan_at_creation=job.plan_at_creation,
            cost_usd_estimate=job.cost_usd_estimate,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
            duration_ms=job.duration_ms,
            parent_job_id=job.parent_job_id,
            revision=job.revision,
        )


class DesignJobListItem(BaseModel):
    """Lighter shape for list endpoint — no enriched_prompt to keep payload small."""

    model_config = ConfigDict(extra="forbid")

    id: str
    status: DesignStatus
    style: DesignStyle
    aspect: DesignAspect
    prompt: str
    artifact_count: int
    thumbnail_url: str | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_domain(cls, job: DesignJob) -> DesignJobListItem:
        thumb = job.artifacts[0].thumbnail_url if job.artifacts else None
        return cls(
            id=job.id,
            status=job.status,
            style=job.request.style,
            aspect=job.request.aspect,
            prompt=job.request.prompt,
            artifact_count=len(job.artifacts),
            thumbnail_url=thumb,
            failure_reason=job.failure_reason.value if job.failure_reason else None,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )


class DesignJobListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jobs: list[DesignJobListItem]
    total: int
    limit: int
    offset: int


class QuotaResponse(BaseModel):
    """GET /design/quota response shape."""

    model_config = ConfigDict(extra="forbid")

    plan: str
    month_bucket: str
    monthly_limit: int
    used: int
    remaining: int
    resets_at: datetime

    @classmethod
    def from_domain(cls, snap: QuotaSnapshot) -> QuotaResponse:
        return cls(
            plan=snap.plan,
            month_bucket=snap.month_bucket,
            monthly_limit=snap.monthly_limit,
            used=snap.used,
            remaining=snap.remaining,
            resets_at=snap.resets_at,
        )


# ---------------------------------------------------------------------------
# Style preset metadata (for UI)
# ---------------------------------------------------------------------------


class StylePresetItem(BaseModel):
    """One style row for GET /design/styles — drives the UI chips."""

    model_config = ConfigDict(extra="forbid")

    id: DesignStyle
    label: str
    description: str
