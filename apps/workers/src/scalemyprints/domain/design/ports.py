"""
Design Engine — ports (Protocol interfaces).

Domain depends on these Protocols, never on concrete adapters.

Adapters NEVER raise — they return Result objects with `error` set
when something goes wrong. The orchestrator decides how to escalate.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.domain.design.enums import (
    DesignAspect,  # noqa: TC001
    DesignStatus,  # noqa: TC001
    DesignStyle,  # noqa: TC001
    FailureReason,  # noqa: TC001
    ImageGenProviderName,  # noqa: TC001
    OutputFormat,  # noqa: TC001
)
from scalemyprints.domain.design.models import (  # noqa: TC001
    DesignArtifact,
    DesignJob,
    ProvenanceRecord,
    QuotaSnapshot,
)

# -----------------------------------------------------------------------------
# Result objects
# -----------------------------------------------------------------------------


class GeneratedImage(BaseModel):
    """One image emitted by an ImageGenProvider, in-memory before storage."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    image_bytes: bytes
    width: int = Field(ge=1)
    height: int = Field(ge=1)
    format: OutputFormat
    provenance: ProvenanceRecord


class ImageGenResult(BaseModel):
    """Adapter return type — multiple variants, optional error."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    images: list[GeneratedImage] = Field(default_factory=list)
    provider: ImageGenProviderName
    duration_ms: int = 0
    error: str | None = None
    failure_reason: FailureReason | None = None


class PromptEnrichmentResult(BaseModel):
    """Adapter return type for the enrichment step."""

    model_config = ConfigDict(frozen=True)

    enriched_prompt: str
    negative_prompt: str | None = None
    duration_ms: int = 0
    error: str | None = None


class StoredArtifact(BaseModel):
    """Result of persisting an in-memory image to durable storage."""

    model_config = ConfigDict(frozen=True)

    storage_path: str
    public_url: str | None = None
    thumbnail_url: str | None = None
    bytes_size: int = Field(ge=0)
    error: str | None = None


class QuotaCheck(BaseModel):
    """Result of a quota pre-check before charging the user."""

    model_config = ConfigDict(frozen=True)

    allowed: bool
    plan: str
    monthly_limit: int  # -1 = unlimited
    used: int
    remaining: int  # -1 = unlimited
    error: str | None = None


# -----------------------------------------------------------------------------
# Ports — Protocol interfaces
# -----------------------------------------------------------------------------


@runtime_checkable
class ImageGenProvider(Protocol):
    """
    Source of generated images (Fal.ai, OpenAI DALL-E, Replicate, etc.).

    Adapters MUST NOT raise. Always return ImageGenResult; on failure,
    set `error` and (if classifiable) `failure_reason`.
    """

    @property
    def provider_name(self) -> ImageGenProviderName: ...

    async def generate(
        self,
        *,
        enriched_prompt: str,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        variant_count: int,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> ImageGenResult: ...


@runtime_checkable
class PromptEnricher(Protocol):
    """
    Turns a user prompt + style + aspect into a production-quality prompt
    optimized for the image-gen provider. Adds POD-specific guidance
    (transparent background hints, no copyrighted entities, readable text).
    """

    async def enrich(
        self,
        *,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        negative_prompt: str | None = None,
    ) -> PromptEnrichmentResult: ...


@runtime_checkable
class DesignStorage(Protocol):
    """Persists rendered images to durable storage and returns URLs."""

    async def store(
        self,
        *,
        user_id: str,
        job_id: str,
        artifact_index: int,
        image_bytes: bytes,
        format: OutputFormat,
    ) -> StoredArtifact: ...

    async def signed_url(
        self,
        storage_path: str,
        ttl_seconds: int = 60 * 60 * 24,
    ) -> str | None: ...


@runtime_checkable
class DesignJobStore(Protocol):
    """Persists DesignJob lifecycle to durable storage."""

    async def create(self, job: DesignJob) -> None: ...

    async def get(self, job_id: str, user_id: str) -> DesignJob | None: ...

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: DesignStatus | None = None,
    ) -> tuple[list[DesignJob], int]: ...  # (jobs, total)

    async def update_status(
        self,
        job_id: str,
        status: DesignStatus,
        *,
        enriched_prompt: str | None = None,
        artifacts: list[DesignArtifact] | None = None,
        failure_reason: FailureReason | None = None,
        failure_message: str | None = None,
        providers_attempted: list[str] | None = None,
        duration_ms: int | None = None,
        cost_usd_estimate: float | None = None,
    ) -> None: ...

    async def soft_delete(self, job_id: str, user_id: str) -> bool: ...


@runtime_checkable
class QuotaService(Protocol):
    """
    Plan-aware monthly quota tracker.

    `pre_check` reads remaining capacity without mutation; the orchestrator
    calls `commit` only after a successful generation so failed jobs do
    not consume the user's allowance.
    """

    async def snapshot(self, user_id: str) -> QuotaSnapshot: ...

    async def pre_check(self, user_id: str, *, requested: int = 1) -> QuotaCheck: ...

    async def commit(self, user_id: str, *, count: int = 1) -> None: ...
