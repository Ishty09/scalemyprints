"""
Shared pytest configuration.

Fixtures here are available to all tests. Keep heavy/integration fixtures
in the appropriate scope (integration/ tests) so unit tests stay fast.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from scalemyprints.core.config import Settings, get_settings
from scalemyprints.domain.shared.clock import FixedClock


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Ensure each test gets a fresh settings instance."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fixed_clock() -> FixedClock:
    """Deterministic clock fixed at 2026-01-15T12:00:00 UTC."""
    return FixedClock(datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC))


@pytest.fixture
def test_settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Settings populated with safe test values."""
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", "a" * 64)
    monkeypatch.setenv("INTERNAL_API_SECRET", "b" * 64)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    get_settings.cache_clear()
    return get_settings()
