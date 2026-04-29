"""Integration tests for trademark endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode
from tests.fixtures import make_record
from tests.integration.conftest import FakeTrademarkAPI


class TestSearchEndpointHappyPath:
    def test_search_returns_200_with_valid_body(self, client: TestClient) -> None:
        body = {
            "phrase": "Zylonka",
            "jurisdictions": ["US"],
            "nice_classes": [25],
            "check_common_law": False,
        }
        response = client.post("/api/v1/trademark/search", json=body)
        assert response.status_code == 200

    def test_search_returns_envelope(self, client: TestClient) -> None:
        body = {
            "phrase": "Zylonka",
            "jurisdictions": ["US"],
            "nice_classes": [25],
            "check_common_law": False,
        }
        payload = client.post("/api/v1/trademark/search", json=body).json()
        assert payload["ok"] is True
        data = payload["data"]
        assert data["phrase"] == "Zylonka"
        assert data["overall_risk_level"] == "safe"
        assert len(data["jurisdictions"]) == 1
        assert data["jurisdictions"][0]["code"] == "US"

    def test_search_propagates_records_to_response(
        self,
        client: TestClient,
        fake_apis: dict[JurisdictionCode, FakeTrademarkAPI],
    ) -> None:
        fake_apis[JurisdictionCode.US].records_to_return = [
            make_record(
                registration_number="98100001",
                status=FilingStatus.REGISTERED,
                nice_class=25,
            ),
        ]
        body = {
            "phrase": "dog mom",
            "jurisdictions": ["US"],
            "nice_classes": [25],
            "check_common_law": False,
        }
        payload = client.post("/api/v1/trademark/search", json=body).json()
        assert payload["ok"] is True
        us = payload["data"]["jurisdictions"][0]
        assert us["active_registrations"] == 1

    def test_search_uses_default_jurisdictions(self, client: TestClient) -> None:
        body = {"phrase": "Zylonka"}
        payload = client.post("/api/v1/trademark/search", json=body).json()
        assert payload["ok"] is True
        codes = {j["code"] for j in payload["data"]["jurisdictions"]}
        assert codes == {"US", "EU", "AU"}


class TestSearchValidation:
    def test_empty_phrase_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "", "nice_classes": [25]},
        )
        assert response.status_code == 400
        body = response.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "validation_error"

    def test_phrase_too_long_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "x" * 201, "nice_classes": [25]},
        )
        assert response.status_code == 400

    def test_invalid_jurisdiction_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "test", "jurisdictions": ["MARS"], "nice_classes": [25]},
        )
        assert response.status_code == 400

    def test_invalid_nice_class_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "test", "nice_classes": [99]},
        )
        assert response.status_code == 400

    def test_empty_jurisdictions_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "test", "jurisdictions": [], "nice_classes": [25]},
        )
        assert response.status_code == 400

    def test_extra_field_rejected_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": "test", "nice_classes": [25], "hack_field": "bad"},
        )
        assert response.status_code == 400

    def test_missing_phrase_rejected_400(self, client: TestClient) -> None:
        response = client.post("/api/v1/trademark/search", json={"nice_classes": [25]})
        assert response.status_code == 400


class TestErrorEnvelopeShape:
    def test_validation_error_has_details(self, client: TestClient) -> None:
        response = client.post("/api/v1/trademark/search", json={"phrase": ""})
        body = response.json()
        assert body["ok"] is False
        assert "code" in body["error"]
        assert "message" in body["error"]
        assert "details" in body["error"]
        assert "errors" in body["error"]["details"]

    def test_error_includes_request_id(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/trademark/search",
            json={"phrase": ""},
            headers={"X-Request-ID": "req_error_test"},
        )
        body = response.json()
        assert body["error"]["request_id"] == "req_error_test"


class TestRateLimiting:
    def test_anonymous_user_hits_free_tier_limit(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """6 anonymous requests in a row → 6th returns 429."""
        monkeypatch.setenv("RATE_LIMIT_TRADEMARK_FREE_TIER", "5")
        # Reset rate limiter (process-wide singleton)
        from scalemyprints.api.middleware.rate_limit import get_rate_limiter
        from scalemyprints.core.config import get_settings

        get_settings.cache_clear()
        get_rate_limiter.cache_clear()

        body = {
            "phrase": "test",
            "jurisdictions": ["US"],
            "nice_classes": [25],
            "check_common_law": False,
        }

        # First 5 succeed
        for _ in range(5):
            r = client.post("/api/v1/trademark/search", json=body)
            assert r.status_code == 200, r.json()

        # 6th exceeds
        r6 = client.post("/api/v1/trademark/search", json=body)
        assert r6.status_code == 429
        body = r6.json()
        assert body["ok"] is False
        assert body["error"]["code"] == "rate_limited"


class TestCORS:
    def test_cors_headers_present(self, client: TestClient) -> None:
        response = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"

    def test_preflight_options(self, client: TestClient) -> None:
        response = client.options(
            "/api/v1/trademark/search",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert response.status_code in (200, 204)
