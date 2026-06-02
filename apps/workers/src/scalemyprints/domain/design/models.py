"""
Design Engine — domain models.

All models frozen (immutable). Pure data shapes; no behavior.
Behavior lives in services (generation_service, prompt_enricher_service).

A "DesignJob" is the persisted unit of work. A user submits a
DesignRequest, the orchestrator turns it into a DesignJob (with status
transitions over its lifetime), and on success a DesignArtifact is
attached pointing at the rendered image(s) in storage.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStatus,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)

# Score / probability bounds
DesignScore = Annotated[int, Field(ge=0, le=100)]


# -----------------------------------------------------------------------------
# Request — what the caller submits
# -----------------------------------------------------------------------------


class DesignRequest(BaseModel):
    """User-facing request payload."""

    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=3, max_length=600)
    style: DesignStyle = DesignStyle.MINIMAL
    aspect: DesignAspect = DesignAspect.SQUARE
    output_format: OutputFormat = OutputFormat.PNG_TRANSPARENT
    variant_count: int = Field(default=1, ge=1, le=4)
    negative_prompt: str | None = Field(default=None, max_length=400)
    seed: int | None = Field(default=None, ge=0)
    parent_job_id: str | None = None  # set when this is an iteration of a prior job


# -----------------------------------------------------------------------------
# Provenance — who/what/when produced this artifact
# -----------------------------------------------------------------------------


class ProvenanceRecord(BaseModel):
    """
    Per-image provenance — required for production-grade audit and to
    let the UI render "made with X model, seed Y" badges.
    """

    model_config = ConfigDict(frozen=True)

    provider: ImageGenProviderName
    model: str
    seed: int | None
    enriched_prompt: str
    raw_prompt: str
    style: DesignStyle
    aspect: DesignAspect
    cost_usd: float | None = None  # filled in by adapters that report cost
    duration_ms: int = 0
    safety_filtered: bool = False
    moderation_flags: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Artifact — the rendered output(s)
# -----------------------------------------------------------------------------


class DesignArtifact(BaseModel):
    """One rendered image variant attached to a DesignJob."""

    model_config = ConfigDict(frozen=True)

    id: str  # uuid
    storage_path: str  # bucket-relative key, e.g., "user-id/job-id/0.png"
    public_url: str | None = None  # signed URL or CDN URL when generated
    thumbnail_url: str | None = None
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    format: OutputFormat
    bytes_size: int = Field(ge=0)
    provenance: ProvenanceRecord


# -----------------------------------------------------------------------------
# Job — the persisted unit of work
# -----------------------------------------------------------------------------


class DesignJob(BaseModel):
    """
    Persisted lifecycle of a design generation request.

    `status` advances QUEUED → ENRICHING → GENERATING → POST_PROCESSING →
    COMPLETED. On failure it becomes FAILED with `failure_reason`.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    request: DesignRequest

    status: DesignStatus
    enriched_prompt: str | None = None
    artifacts: list[DesignArtifact] = Field(default_factory=list)

    failure_reason: FailureReason | None = None
    failure_message: str | None = None
    providers_attempted: list[str] = Field(default_factory=list)

    plan_at_creation: str | None = None  # tier slug at time of creation
    quota_consumed: int = 0
    cost_usd_estimate: float | None = None

    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    duration_ms: int = 0

    parent_job_id: str | None = None
    revision: int = 0  # 0 for original, increments per iterate


# -----------------------------------------------------------------------------
# Quota snapshot
# -----------------------------------------------------------------------------


class QuotaSnapshot(BaseModel):
    """Returned by GET /design/quota — what the UI shows in the badge."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    plan: str  # "free", "core_bundle", "pro_bundle", etc.
    month_bucket: str  # YYYY-MM
    monthly_limit: int  # -1 = unlimited
    used: int
    remaining: int  # -1 = unlimited
    resets_at: datetime
