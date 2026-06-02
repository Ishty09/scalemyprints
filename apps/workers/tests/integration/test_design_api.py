"""
Integration tests for design endpoints — full request/response flow with stubs.

Mounts the design router on a minimal FastAPI app and overrides only the
ServiceContainer wiring needed for design endpoints. Avoids depending on
the full create_app() (which pulls in niche/trademark adapters that may
not be importable in test environments).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scalemyprints.api.deps import get_service_container
from scalemyprints.api.middleware.auth import CurrentUser, get_current_user
from scalemyprints.api.middleware.rate_limit import get_rate_limiter
from scalemyprints.api.routes.design import router as design_router
from scalemyprints.domain.design.enums import (
    FailureReason,
)
from scalemyprints.domain.design.generation_service import DesignGenerationService
from tests.domain.design.conftest import (
    StubImageGenProvider,
    StubJobStore,
    StubPromptEnricher,
    StubQuotaService,
    StubStorage,
    build_generated_image,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class _NoopRateLimiter:
    """Rate limiter that never rejects — keeps integration tests deterministic."""

    async def check(self, *, key: str, limit: int, window_seconds: int) -> None:
        return None


class _StubContainer:
    """Minimal ServiceContainer-shaped object for design routes."""

    def __init__(
        self,
        *,
        enricher: StubPromptEnricher,
        image_gen: StubImageGenProvider,
        storage: StubStorage,
        jobs: StubJobStore,
        quota: StubQuotaService,
    ) -> None:
        self.design_image_gen = image_gen
        self.design_job_store = jobs
        self.design_quota = quota
        self.design_storage = storage
        self._enricher = enricher
        self._image_gen = image_gen
        self._storage = storage
        self._jobs = jobs
        self._quota = quota

    def build_design_generation_service(self) -> DesignGenerationService:
        return DesignGenerationService(
            prompt_enricher=self._enricher,
            image_gen_provider=self._image_gen,
            storage=self._storage,
            job_store=self._jobs,
            quota=self._quota,
        )


@pytest.fixture
def fake_user() -> CurrentUser:
    return CurrentUser(id="user-123", email="user@test.dev", is_anonymous=False)


@pytest.fixture
def stubs() -> dict[str, Any]:
    return {
        "enricher": StubPromptEnricher(),
        "image_gen": StubImageGenProvider(images=[build_generated_image()]),
        "storage": StubStorage(),
        "jobs": StubJobStore(),
        "quota": StubQuotaService(),
    }


@pytest.fixture
def design_app(fake_user: CurrentUser, stubs: dict[str, Any]) -> FastAPI:
    app = FastAPI()
    app.include_router(design_router)

    container = _StubContainer(
        enricher=stubs["enricher"],
        image_gen=stubs["image_gen"],
        storage=stubs["storage"],
        jobs=stubs["jobs"],
        quota=stubs["quota"],
    )

    app.dependency_overrides[get_current_user] = lambda: fake_user
    app.dependency_overrides[get_service_container] = lambda: container
    app.dependency_overrides[get_rate_limiter] = _NoopRateLimiter
    return app


@pytest.fixture
def client(design_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(design_app) as c:
        yield c


@pytest.mark.integration
class TestDesignGenerateEndpoint:
    def test_happy_path_returns_completed_job(
        self, client: TestClient, stubs: dict[str, Any]
    ) -> None:
        response = client.post(
            "/api/v1/design/generate",
            json={
                "prompt": "dog mom with iced coffee",
                "style": "minimal",
                "aspect": "square",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["ok"] is True
        assert body["data"]["status"] == "completed"
        assert len(body["data"]["artifacts"]) == 1
        assert stubs["quota"].committed == 1

    def test_quota_exceeded_returns_402(self, client: TestClient, stubs: dict[str, Any]) -> None:
        stubs["quota"].used = 999
        stubs["quota"].monthly_limit = 5

        response = client.post(
            "/api/v1/design/generate",
            json={"prompt": "dog mom"},
        )
        assert response.status_code == 402
        assert response.json()["detail"]["code"] == "quota_exceeded"

    def test_provider_unavailable_returns_503(
        self,
        fake_user: CurrentUser,
        stubs: dict[str, Any],
    ) -> None:
        stubs["image_gen"] = StubImageGenProvider(
            images=[],
            error="provider_timeout",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
        app = FastAPI()
        app.include_router(design_router)
        container = _StubContainer(
            enricher=stubs["enricher"],
            image_gen=stubs["image_gen"],
            storage=stubs["storage"],
            jobs=stubs["jobs"],
            quota=stubs["quota"],
        )
        app.dependency_overrides[get_current_user] = lambda: fake_user
        app.dependency_overrides[get_service_container] = lambda: container
        app.dependency_overrides[get_rate_limiter] = _NoopRateLimiter

        with TestClient(app) as client:
            response = client.post(
                "/api/v1/design/generate",
                json={"prompt": "dog mom"},
            )
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "provider_unavailable"

    def test_validation_rejects_short_prompt(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/design/generate",
            json={"prompt": "ab"},
        )
        assert response.status_code == 422


@pytest.mark.integration
class TestDesignJobsEndpoints:
    def test_get_quota_returns_snapshot(self, client: TestClient) -> None:
        response = client.get("/api/v1/design/quota")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["plan"] == "core_bundle"
        assert body["data"]["monthly_limit"] == 200

    def test_get_styles_lists_presets(self, client: TestClient) -> None:
        response = client.get("/api/v1/design/styles")
        assert response.status_code == 200
        items = response.json()["data"]
        assert len(items) >= 5
        ids = {item["id"] for item in items}
        assert "minimal" in ids
        assert "vintage" in ids

    def test_list_jobs_returns_users_jobs_only(self, client: TestClient) -> None:
        client.post("/api/v1/design/generate", json={"prompt": "dog mom"})
        response = client.get("/api/v1/design/jobs")
        assert response.status_code == 200
        body = response.json()
        assert body["data"]["total"] == 1
        assert len(body["data"]["jobs"]) == 1

    def test_get_unknown_job_returns_404(self, client: TestClient) -> None:
        response = client.get("/api/v1/design/jobs/nonexistent")
        assert response.status_code == 404

    def test_delete_then_get_returns_404(self, client: TestClient) -> None:
        gen = client.post("/api/v1/design/generate", json={"prompt": "dog mom"})
        job_id = gen.json()["data"]["id"]

        delete = client.delete(f"/api/v1/design/jobs/{job_id}")
        assert delete.status_code == 200
        assert delete.json()["data"]["deleted"] is True

        fetch = client.get(f"/api/v1/design/jobs/{job_id}")
        assert fetch.status_code == 404
