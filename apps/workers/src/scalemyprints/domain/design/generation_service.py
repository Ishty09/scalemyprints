"""
Design generation orchestrator.

Owns the full lifecycle of a DesignJob:

  1. Validate request + quota pre-check
  2. Persist the QUEUED job
  3. Enrich the prompt (LLM)
  4. Call image-gen provider chain (first-success-wins)
  5. Store rendered images in durable storage
  6. Update the job to COMPLETED with provenance
  7. Commit quota (only on success)

Failure at any step transitions the job to FAILED with a categorized
failure_reason. The orchestrator never raises — callers receive a
DesignJob whose status they must inspect.

This is the only place that knows about all of: enricher, image-gen,
storage, quota, and job-store. Routes call this service; nothing else.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import (
    DesignStatus,
    FailureReason,
)
from scalemyprints.domain.design.models import (
    DesignArtifact,
    DesignJob,
    DesignRequest,
)

if TYPE_CHECKING:
    from scalemyprints.domain.design.ports import (
        DesignJobStore,
        DesignStorage,
        ImageGenProvider,
        PromptEnricher,
        QuotaService,
    )

logger = get_logger(__name__)


class DesignGenerationService:
    """High-level coordinator for design generation."""

    def __init__(
        self,
        *,
        prompt_enricher: PromptEnricher,
        image_gen_provider: ImageGenProvider,
        storage: DesignStorage,
        job_store: DesignJobStore,
        quota: QuotaService,
    ) -> None:
        self._enricher = prompt_enricher
        self._image_gen = image_gen_provider
        self._storage = storage
        self._jobs = job_store
        self._quota = quota

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        *,
        user_id: str,
        request: DesignRequest,
    ) -> DesignJob:
        """
        Run the full pipeline synchronously and return the final DesignJob.

        For the MVP we run inline (image-gen completes in 2-15s with Flux
        Schnell / DALL-E). When we move to slower providers or batch we
        will queue this work; the surface stays the same.
        """
        start = time.monotonic()
        job_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        log = logger.bind(
            job_id=job_id,
            user_id=user_id,
            style=request.style.value,
            aspect=request.aspect.value,
            variant_count=request.variant_count,
        )

        # ---- 1. Quota pre-check ------------------------------------------------
        quota_check = await self._quota.pre_check(user_id, requested=request.variant_count)
        if not quota_check.allowed:
            log.info(
                "design_quota_exceeded",
                used=quota_check.used,
                limit=quota_check.monthly_limit,
            )
            return self._build_failed_job(
                job_id=job_id,
                user_id=user_id,
                request=request,
                now=now,
                reason=FailureReason.QUOTA_EXCEEDED,
                message=(f"Monthly limit reached ({quota_check.used}/{quota_check.monthly_limit})"),
                plan=quota_check.plan,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # ---- 2. Persist QUEUED job ---------------------------------------------
        job = DesignJob(
            id=job_id,
            user_id=user_id,
            request=request,
            status=DesignStatus.QUEUED,
            created_at=now,
            updated_at=now,
            plan_at_creation=quota_check.plan,
            parent_job_id=request.parent_job_id,
        )
        await self._jobs.create(job)
        log.info("design_job_created", plan=quota_check.plan)

        # ---- 3. Enrich the prompt ----------------------------------------------
        await self._jobs.update_status(job_id, DesignStatus.ENRICHING)
        enrichment = await self._enricher.enrich(
            raw_prompt=request.prompt,
            style=request.style,
            aspect=request.aspect,
            output_format=request.output_format,
            negative_prompt=request.negative_prompt,
        )
        if enrichment.error:
            log.warning("design_enrichment_error", error=enrichment.error)

        enriched_prompt = enrichment.enriched_prompt or request.prompt
        effective_negative = enrichment.negative_prompt or request.negative_prompt

        # ---- 4. Generate via provider chain ------------------------------------
        await self._jobs.update_status(
            job_id,
            DesignStatus.GENERATING,
            enriched_prompt=enriched_prompt,
        )
        gen_result = await self._image_gen.generate(
            enriched_prompt=enriched_prompt,
            raw_prompt=request.prompt,
            style=request.style,
            aspect=request.aspect,
            output_format=request.output_format,
            variant_count=request.variant_count,
            negative_prompt=effective_negative,
            seed=request.seed,
        )

        if gen_result.error or not gen_result.images:
            reason = gen_result.failure_reason or FailureReason.PROVIDER_UNAVAILABLE
            log.warning(
                "design_generation_failed",
                provider=gen_result.provider.value,
                error=gen_result.error,
                reason=reason.value,
            )
            await self._jobs.update_status(
                job_id,
                DesignStatus.FAILED,
                failure_reason=reason,
                failure_message=gen_result.error or "no_images_returned",
                providers_attempted=[gen_result.provider.value],
                duration_ms=int((time.monotonic() - start) * 1000),
            )
            return await self._reload(job_id, user_id)

        # ---- 5. Persist artifacts to storage -----------------------------------
        await self._jobs.update_status(job_id, DesignStatus.POST_PROCESSING)
        artifacts: list[DesignArtifact] = []
        for index, image in enumerate(gen_result.images):
            stored = await self._storage.store(
                user_id=user_id,
                job_id=job_id,
                artifact_index=index,
                image_bytes=image.image_bytes,
                format=image.format,
            )
            if stored.error:
                log.warning(
                    "design_storage_failed",
                    artifact_index=index,
                    error=stored.error,
                )
                await self._jobs.update_status(
                    job_id,
                    DesignStatus.FAILED,
                    failure_reason=FailureReason.STORAGE_FAILURE,
                    failure_message=stored.error,
                    providers_attempted=[gen_result.provider.value],
                    duration_ms=int((time.monotonic() - start) * 1000),
                )
                return await self._reload(job_id, user_id)

            artifacts.append(
                DesignArtifact(
                    id=str(uuid.uuid4()),
                    storage_path=stored.storage_path,
                    public_url=stored.public_url,
                    thumbnail_url=stored.thumbnail_url,
                    width=image.width,
                    height=image.height,
                    format=image.format,
                    bytes_size=stored.bytes_size,
                    provenance=image.provenance,
                )
            )

        # ---- 6. Mark COMPLETED -------------------------------------------------
        duration_ms = int((time.monotonic() - start) * 1000)
        cost_estimate = sum((a.provenance.cost_usd or 0.0) for a in artifacts) or None

        await self._jobs.update_status(
            job_id,
            DesignStatus.COMPLETED,
            enriched_prompt=enriched_prompt,
            artifacts=artifacts,
            providers_attempted=[gen_result.provider.value],
            duration_ms=duration_ms,
            cost_usd_estimate=cost_estimate,
        )
        log.info(
            "design_job_completed",
            provider=gen_result.provider.value,
            artifact_count=len(artifacts),
            duration_ms=duration_ms,
        )

        # ---- 7. Commit quota ---------------------------------------------------
        try:
            await self._quota.commit(user_id, count=len(artifacts))
        except Exception as e:
            log.exception("design_quota_commit_failed", error=str(e))

        return await self._reload(job_id, user_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _reload(self, job_id: str, user_id: str) -> DesignJob:
        """Refetch the canonical job state after we've mutated it."""
        job = await self._jobs.get(job_id, user_id)
        if job is None:
            # Should be impossible — we just created it. Surface as failure.
            now = datetime.now(UTC)
            return DesignJob(
                id=job_id,
                user_id=user_id,
                request=DesignRequest(prompt="?"),
                status=DesignStatus.FAILED,
                failure_reason=FailureReason.INTERNAL,
                failure_message="job_disappeared_after_write",
                created_at=now,
                updated_at=now,
            )
        return job

    @staticmethod
    def _build_failed_job(
        *,
        job_id: str,
        user_id: str,
        request: DesignRequest,
        now: datetime,
        reason: FailureReason,
        message: str,
        plan: str | None,
        duration_ms: int,
    ) -> DesignJob:
        return DesignJob(
            id=job_id,
            user_id=user_id,
            request=request,
            status=DesignStatus.FAILED,
            failure_reason=reason,
            failure_message=message,
            plan_at_creation=plan,
            created_at=now,
            updated_at=now,
            duration_ms=duration_ms,
        )
