"""Unit tests for the velocity analyzer."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scalemyprints.domain.spy.enums import VelocityClass
from scalemyprints.domain.spy.models import ListingSnapshot
from scalemyprints.domain.spy.velocity_service import VelocityAnalyzer


@pytest.fixture
def analyzer() -> VelocityAnalyzer:
    return VelocityAnalyzer()


def _series(sales: list[float], listing_id: str = "L1") -> list[ListingSnapshot]:
    """Build a snapshot series where each entry is 1 day apart."""
    now = datetime.now(UTC)
    snaps: list[ListingSnapshot] = []
    for i, s in enumerate(reversed(sales)):
        snaps.append(
            ListingSnapshot(
                listing_id=listing_id,
                captured_at=now - timedelta(days=i),
                est_daily_sales=s,
            )
        )
    return list(reversed(snaps))  # newest last


@pytest.mark.asyncio
async def test_returns_none_when_too_few_samples(analyzer: VelocityAnalyzer) -> None:
    result = await analyzer.analyze("L1", _series([1.0, 1.1, 1.0]))
    assert result is None


@pytest.mark.asyncio
async def test_steady_returns_none(analyzer: VelocityAnalyzer) -> None:
    # 14 days of ~constant sales — should NOT emit a signal
    result = await analyzer.analyze("L1", _series([2.0] * 14))
    assert result is None


@pytest.mark.asyncio
async def test_detects_spike(analyzer: VelocityAnalyzer) -> None:
    # 13 days at 2/day, latest at 25/day → big spike
    sales = [2.0] * 13 + [25.0]
    result = await analyzer.analyze("L1", _series(sales))
    assert result is not None
    assert result.velocity_class in (VelocityClass.SPIKING, VelocityClass.EXPLOSIVE)
    assert result.z_score > 2.5
    assert result.sales_baseline is not None and result.sales_baseline < 5.0
    assert result.sales_current is not None and result.sales_current >= 25.0
    assert result.note is not None


@pytest.mark.asyncio
async def test_emits_signal_with_note_and_confidence(
    analyzer: VelocityAnalyzer,
) -> None:
    # Stable baseline + clear bump → expect a signal with non-empty note
    # and confidence > 0
    sales = [5.0] * 13 + [12.0]
    result = await analyzer.analyze("L1", _series(sales))
    assert result is not None
    assert result.confidence > 0
    assert result.note is not None and "z=" in result.note


@pytest.mark.asyncio
async def test_filters_out_nones(analyzer: VelocityAnalyzer) -> None:
    """Snapshots without est_daily_sales should be silently dropped."""
    now = datetime.now(UTC)
    snaps = [
        ListingSnapshot(listing_id="L1", captured_at=now - timedelta(days=i))
        for i in range(10)
    ] + _series([2.0] * 14)
    result = await analyzer.analyze("L1", snaps)
    # Should still emit a steady (None) result, not crash
    assert result is None or result.velocity_class in VelocityClass
