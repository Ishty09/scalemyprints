"""Tests for Clock protocol and implementations."""

from __future__ import annotations

from datetime import UTC, datetime, timezone

import pytest

from scalemyprints.domain.shared.clock import FixedClock, SystemClock


class TestSystemClock:
    def test_now_returns_timezone_aware(self) -> None:
        clock = SystemClock()
        now = clock.now()
        assert now.tzinfo is not None


class TestFixedClock:
    def test_returns_fixed_time(self) -> None:
        fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(fixed_time)
        assert clock.now() == fixed_time

    def test_requires_timezone_aware(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            FixedClock(datetime(2026, 1, 1))  # noqa: DTZ001 — intentional test

    def test_advance_by_seconds(self) -> None:
        fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(fixed_time)
        clock.advance(seconds=60)
        assert clock.now() == datetime(2026, 1, 1, 0, 1, 0, tzinfo=UTC)

    def test_advance_by_days(self) -> None:
        fixed_time = datetime(2026, 1, 1, tzinfo=UTC)
        clock = FixedClock(fixed_time)
        clock.advance(days=7)
        assert clock.now() == datetime(2026, 1, 8, tzinfo=UTC)
