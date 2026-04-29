"""Tests for NoOpCommonLawChecker."""

from __future__ import annotations

import pytest

from scalemyprints.infrastructure.common_law.no_op import NoOpCommonLawChecker


class TestNoOpCommonLawChecker:
    async def test_returns_zero_density(self) -> None:
        checker = NoOpCommonLawChecker()
        density = await checker.estimate_density("dog mom")
        assert density == 0.0

    async def test_never_raises(self) -> None:
        checker = NoOpCommonLawChecker()
        # Even with weird inputs, should not raise
        await checker.estimate_density("")
        await checker.estimate_density("a" * 1000)
