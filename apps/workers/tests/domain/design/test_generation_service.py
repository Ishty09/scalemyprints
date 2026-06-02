"""DesignGenerationService — happy path, quota gate, provider failures, storage failures."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStatus,
    DesignStyle,
    FailureReason,
    OutputFormat,
)
from scalemyprints.domain.design.generation_service import DesignGenerationService
from scalemyprints.domain.design.models import DesignRequest
from tests.domain.design.conftest import (
    StubImageGenProvider,
    StubJobStore,
    StubPromptEnricher,
    StubQuotaService,
    StubStorage,
    build_generated_image,
)


def _service(
    *,
    images: list | None = None,
    image_error: str | None = None,
    image_failure: FailureReason | None = None,
    storage_error: str | None = None,
    quota_used: int = 0,
    quota_limit: int = 200,
) -> tuple[DesignGenerationService, StubJobStore, StubQuotaService, StubStorage]:
    job_store = StubJobStore()
    quota = StubQuotaService(used=quota_used, monthly_limit=quota_limit)
    storage = StubStorage(error=storage_error)
    image_gen = StubImageGenProvider(
        images=images if images is not None else [build_generated_image()],
        error=image_error,
        failure_reason=image_failure,
    )
    enricher = StubPromptEnricher()
    service = DesignGenerationService(
        prompt_enricher=enricher,
        image_gen_provider=image_gen,
        storage=storage,
        job_store=job_store,
        quota=quota,
    )
    return service, job_store, quota, storage


def _request(variant_count: int = 1) -> DesignRequest:
    return DesignRequest(
        prompt="dog mom with iced coffee",
        style=DesignStyle.MINIMAL,
        aspect=DesignAspect.SQUARE,
        output_format=OutputFormat.PNG_TRANSPARENT,
        variant_count=variant_count,
    )


@pytest.mark.unit
class TestDesignGenerationServiceHappyPath:
    async def test_completes_and_records_artifacts(self) -> None:
        service, jobs, quota, _storage = _service()
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.COMPLETED
        assert len(result.artifacts) == 1
        assert result.artifacts[0].public_url is not None
        assert result.enriched_prompt == "ENRICHED"
        # Quota committed for successful generation.
        assert quota.committed == 1
        # Job lifecycle progressed through expected states.
        states = [s for _, s in jobs.history]
        assert DesignStatus.ENRICHING in states
        assert DesignStatus.GENERATING in states
        assert DesignStatus.POST_PROCESSING in states
        assert DesignStatus.COMPLETED in states

    async def test_multiple_variants(self) -> None:
        images = [build_generated_image() for _ in range(3)]
        service, _, quota, storage = _service(images=images)
        result = await service.submit(user_id="u1", request=_request(variant_count=3))

        assert result.status == DesignStatus.COMPLETED
        assert len(result.artifacts) == 3
        assert len(storage.stored) == 3
        assert quota.committed == 3


@pytest.mark.unit
class TestDesignGenerationServiceQuota:
    async def test_quota_exceeded_short_circuits(self) -> None:
        service, jobs, quota, _ = _service(quota_used=200, quota_limit=200)
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.FAILED
        assert result.failure_reason == FailureReason.QUOTA_EXCEEDED
        # No quota commit; no job created.
        assert quota.committed == 0
        assert jobs.history == []

    async def test_unlimited_plan_proceeds(self) -> None:
        service, _, quota, _ = _service(quota_limit=-1, quota_used=999)
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.COMPLETED
        assert quota.committed == 1


@pytest.mark.unit
class TestDesignGenerationServiceFailures:
    async def test_provider_unavailable_fails_without_quota_charge(self) -> None:
        service, _, quota, storage = _service(
            images=[],
            image_error="provider_timeout",
            image_failure=FailureReason.PROVIDER_UNAVAILABLE,
        )
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.FAILED
        assert result.failure_reason == FailureReason.PROVIDER_UNAVAILABLE
        assert result.failure_message == "provider_timeout"
        assert quota.committed == 0
        assert storage.stored == []

    async def test_storage_failure_marks_failed(self) -> None:
        service, _, quota, storage = _service(storage_error="upload_failed")
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.FAILED
        assert result.failure_reason == FailureReason.STORAGE_FAILURE
        assert quota.committed == 0
        # Attempted upload once.
        assert len(storage.stored) == 1

    async def test_policy_violation_returns_terminal_failure(self) -> None:
        service, _, quota, _ = _service(
            images=[],
            image_error="content_policy",
            image_failure=FailureReason.POLICY_VIOLATION,
        )
        result = await service.submit(user_id="u1", request=_request())

        assert result.status == DesignStatus.FAILED
        assert result.failure_reason == FailureReason.POLICY_VIOLATION
        assert quota.committed == 0
