"""Integration tests for health endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_envelope(self, client: TestClient) -> None:
        body = client.get("/health").json()
        assert body["ok"] is True
        assert body["data"]["status"] == "ok"
        assert "version" in body["data"]

    def test_health_has_request_id_header(self, client: TestClient) -> None:
        response = client.get("/health")
        assert "X-Request-ID" in response.headers
        assert response.headers["X-Request-ID"].startswith("req_")

    def test_honors_incoming_request_id(self, client: TestClient) -> None:
        custom_id = "req_custom123"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.headers["X-Request-ID"] == custom_id


class TestReadyEndpoint:
    def test_ready_returns_200(self, client: TestClient) -> None:
        response = client.get("/ready")
        assert response.status_code == 200

    def test_ready_reports_checks(self, client: TestClient) -> None:
        body = client.get("/ready").json()
        assert body["ok"] is True
        assert body["data"]["status"] == "ready"
        assert "checks" in body["data"]


class TestRootEndpoint:
    def test_root_returns_name(self, client: TestClient) -> None:
        body = client.get("/").json()
        assert body["name"] == "ScaleMyPrints API"
