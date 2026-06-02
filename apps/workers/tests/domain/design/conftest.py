"""Shared stubs for design-engine domain tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStatus,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)
from scalemyprints.domain.design.models import (
    DesignArtifact,
    DesignJob,
    ProvenanceRecord,
    QuotaSnapshot,
)
from scalemyprints.domain.design.ports import (
    GeneratedImage,
    ImageGenResult,
    PromptEnrichmentResult,
    QuotaCheck,
    StoredArtifact,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

# ---------------------------------------------------------------------------
# In-memory stand-ins
# ---------------------------------------------------------------------------


class StubPromptEnricher:
    def __init__(
        self,
        *,
        enriched_prompt: str = "ENRICHED",
        negative_prompt: str = "ugly",
        error: str | None = None,
    ) -> None:
        self.enriched_prompt = enriched_prompt
        self.negative_prompt = negative_prompt
        self.error = error
        self.calls = 0

    async def enrich(self, **kwargs: object) -> PromptEnrichmentResult:
        self.calls += 1
        return PromptEnrichmentResult(
            enriched_prompt=self.enriched_prompt,
            negative_prompt=self.negative_prompt,
            duration_ms=10,
            error=self.error,
        )


class StubImageGenProvider:
    def __init__(
        self,
        *,
        provider: ImageGenProviderName = ImageGenProviderName.FAL_FLUX_SCHNELL,
        images: Iterable[GeneratedImage] | None = None,
        error: str | None = None,
        failure_reason: FailureReason | None = None,
    ) -> None:
        self._provider = provider
        self._images = list(images or [])
        self._error = error
        self._failure_reason = failure_reason
        self.calls = 0

    @property
    def provider_name(self) -> ImageGenProviderName:
        return self._provider

    async def generate(self, **kwargs: object) -> ImageGenResult:
        self.calls += 1
        return ImageGenResult(
            images=list(self._images),
            provider=self._provider,
            duration_ms=20,
            error=self._error,
            failure_reason=self._failure_reason,
        )


class StubStorage:
    def __init__(self, *, error: str | None = None) -> None:
        self.error = error
        self.stored: list[tuple[str, str, int, int]] = []

    async def store(
        self,
        *,
        user_id: str,
        job_id: str,
        artifact_index: int,
        image_bytes: bytes,
        format: OutputFormat,
    ) -> StoredArtifact:
        self.stored.append((user_id, job_id, artifact_index, len(image_bytes)))
        if self.error:
            return StoredArtifact(
                storage_path=f"{user_id}/{job_id}/{artifact_index}",
                bytes_size=len(image_bytes),
                error=self.error,
            )
        path = f"{user_id}/{job_id}/{artifact_index}.png"
        return StoredArtifact(
            storage_path=path,
            public_url=f"https://stub/{path}",
            thumbnail_url=f"https://stub/{path}",
            bytes_size=len(image_bytes),
            error=None,
        )

    async def signed_url(self, storage_path: str, ttl_seconds: int = 60 * 60 * 24) -> str | None:
        return f"https://stub/{storage_path}"


class StubJobStore:
    def __init__(self) -> None:
        self.jobs: dict[str, DesignJob] = {}
        self.history: list[tuple[str, DesignStatus]] = []

    async def create(self, job: DesignJob) -> None:
        self.jobs[job.id] = job

    async def get(self, job_id: str, user_id: str) -> DesignJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.user_id != user_id:
            return None
        return job

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: DesignStatus | None = None,
    ) -> tuple[list[DesignJob], int]:
        matching = [
            j
            for j in self.jobs.values()
            if j.user_id == user_id and (status is None or j.status == status)
        ]
        return matching[offset : offset + limit], len(matching)

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
    ) -> None:
        self.history.append((job_id, status))
        job = self.jobs.get(job_id)
        if job is None:
            return
        self.jobs[job_id] = job.model_copy(
            update={
                "status": status,
                "enriched_prompt": (
                    enriched_prompt if enriched_prompt is not None else job.enriched_prompt
                ),
                "artifacts": (artifacts if artifacts is not None else job.artifacts),
                "failure_reason": (
                    failure_reason if failure_reason is not None else job.failure_reason
                ),
                "failure_message": (
                    failure_message if failure_message is not None else job.failure_message
                ),
                "providers_attempted": (
                    providers_attempted
                    if providers_attempted is not None
                    else job.providers_attempted
                ),
                "duration_ms": (duration_ms if duration_ms is not None else job.duration_ms),
                "cost_usd_estimate": (
                    cost_usd_estimate if cost_usd_estimate is not None else job.cost_usd_estimate
                ),
            }
        )

    async def soft_delete(self, job_id: str, user_id: str) -> bool:
        if job_id in self.jobs and self.jobs[job_id].user_id == user_id:
            del self.jobs[job_id]
            return True
        return False


class StubQuotaService:
    def __init__(
        self,
        *,
        plan: str = "core_bundle",
        monthly_limit: int = 200,
        used: int = 0,
    ) -> None:
        self.plan = plan
        self.monthly_limit = monthly_limit
        self.used = used
        self.committed = 0

    async def snapshot(self, user_id: str) -> QuotaSnapshot:
        return QuotaSnapshot(
            user_id=user_id,
            plan=self.plan,
            month_bucket="2026-05",
            monthly_limit=self.monthly_limit,
            used=self.used,
            remaining=max(self.monthly_limit - self.used, 0),
            resets_at=datetime(2026, 6, 1, tzinfo=UTC),
        )

    async def pre_check(self, user_id: str, *, requested: int = 1) -> QuotaCheck:
        if self.monthly_limit == -1:
            return QuotaCheck(
                allowed=True,
                plan=self.plan,
                monthly_limit=-1,
                used=self.used,
                remaining=-1,
            )
        return QuotaCheck(
            allowed=(self.used + requested) <= self.monthly_limit,
            plan=self.plan,
            monthly_limit=self.monthly_limit,
            used=self.used,
            remaining=max(self.monthly_limit - self.used, 0),
        )

    async def commit(self, user_id: str, *, count: int = 1) -> None:
        self.committed += count
        self.used += count


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def build_generated_image(
    *,
    raw: str = "raw",
    enriched: str = "enriched",
) -> GeneratedImage:
    return GeneratedImage(
        image_bytes=b"\x89PNG\r\n\x1a\nfake",
        width=1024,
        height=1024,
        format=OutputFormat.PNG_TRANSPARENT,
        provenance=ProvenanceRecord(
            provider=ImageGenProviderName.FAL_FLUX_SCHNELL,
            model="fal-ai/flux/schnell",
            seed=42,
            enriched_prompt=enriched,
            raw_prompt=raw,
            style=DesignStyle.MINIMAL,
            aspect=DesignAspect.SQUARE,
            cost_usd=0.003,
            duration_ms=20,
        ),
    )
