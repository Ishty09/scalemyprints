"""
Clock abstraction for deterministic testing.

Never call `datetime.now()` directly in domain logic; inject a Clock instead.
This allows tests to freeze time without monkey-patching.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Protocol for time providers."""

    def now(self) -> datetime: ...


class SystemClock:
    """Default Clock implementation using system time (UTC)."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """
    Clock that returns a fixed time — for tests.

    Example:
        clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
        assert clock.now() == datetime(2026, 1, 1, tzinfo=UTC)
    """

    def __init__(self, fixed_time: datetime) -> None:
        if fixed_time.tzinfo is None:
            raise ValueError("FixedClock requires timezone-aware datetime")
        self._fixed_time = fixed_time

    def now(self) -> datetime:
        return self._fixed_time

    def advance(self, **kwargs: int) -> None:
        """Advance the fixed time by the given duration."""
        from datetime import timedelta

        self._fixed_time = self._fixed_time + timedelta(**kwargs)
