"""
Velocity analyzer — classifies a listing's recent sales trajectory.

Inputs: a series of ListingSnapshot rows for one listing.

Outputs: a VelocitySignal (or None if not enough signal).

Algorithm:
  1. Build a daily series of `est_daily_sales` from the snapshots.
  2. Drop empties; require at least 5 days of data.
  3. Baseline = trimmed-mean of the older portion (drop first/last
     20%, average the middle).
  4. Current = most recent 24h (or last snapshot).
  5. Standard deviation over the older portion.
  6. z = (current - baseline) / max(stdev, 0.5)
  7. Map z → VelocityClass via bucket thresholds.
  8. Confidence = min(1.0, sample_count / 14).

This is intentionally simple and explainable. We can swap in a
proper time-series model (Prophet, NeuralProphet) once we have the
volume to justify it.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime, timedelta

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import VelocityClass
from scalemyprints.domain.spy.models import (
    ListingSnapshot,
    VelocitySignal,
)

logger = get_logger(__name__)


MIN_SAMPLES = 5
SPIKING_Z = 2.5
EXPLOSIVE_Z = 4.0
RISING_Z = 1.0
MIN_STDEV = 0.5            # floor so a stable series doesn't divide by zero
TRIM_RATIO = 0.2


class VelocityAnalyzer:
    """Pure analyzer — no I/O, no side effects."""

    async def analyze(
        self,
        listing_id: str,
        snapshots: list[ListingSnapshot],
    ) -> VelocitySignal | None:
        # Filter to snapshots that carry a sales estimate
        series = sorted(
            (s for s in snapshots if s.est_daily_sales is not None),
            key=lambda s: s.captured_at,
        )

        if len(series) < MIN_SAMPLES:
            logger.debug(
                "velocity_insufficient_samples",
                listing_id=listing_id,
                samples=len(series),
            )
            return None

        # Split into baseline (older) and current (latest)
        latest = series[-1]
        baseline_samples = series[:-1]
        sales = [s.est_daily_sales for s in baseline_samples if s.est_daily_sales is not None]

        if not sales:
            return None

        # Trim outliers
        trimmed = _trimmed(sales, TRIM_RATIO)
        baseline = statistics.fmean(trimmed) if trimmed else statistics.fmean(sales)
        stdev = statistics.pstdev(trimmed) if len(trimmed) >= 2 else MIN_STDEV
        stdev = max(stdev, MIN_STDEV)

        current = latest.est_daily_sales or 0.0
        z = (current - baseline) / stdev

        velocity_class = _classify_z(z)
        if velocity_class == VelocityClass.DORMANT:
            # Don't emit signals for boring listings
            return None
        if velocity_class == VelocityClass.STEADY:
            return None

        # 7-day deltas for human-readable context
        seven_days_ago = latest.captured_at - timedelta(days=7)
        older = next(
            (s for s in series if s.captured_at <= seven_days_ago),
            None,
        )
        favs_delta = (
            latest.favorites - older.favorites
            if older and older.favorites is not None and latest.favorites is not None
            else None
        )
        reviews_delta = (
            latest.reviews_count - older.reviews_count
            if older and older.reviews_count is not None and latest.reviews_count is not None
            else None
        )

        confidence = min(1.0, len(series) / 14.0)

        return VelocitySignal(
            listing_id=listing_id,
            captured_at=latest.captured_at or datetime.now(UTC),
            velocity_class=velocity_class,
            z_score=round(z, 3),
            sales_baseline=round(baseline, 3),
            sales_current=round(current, 3),
            favorites_delta_7d=favs_delta,
            reviews_delta_7d=reviews_delta,
            confidence=round(confidence, 3),
            note=_note(velocity_class, z, baseline, current),
        )


def _classify_z(z: float) -> VelocityClass:
    if z >= EXPLOSIVE_Z:
        return VelocityClass.EXPLOSIVE
    if z >= SPIKING_Z:
        return VelocityClass.SPIKING
    if z >= RISING_Z:
        return VelocityClass.RISING
    return VelocityClass.STEADY


def _trimmed(values: list[float], ratio: float) -> list[float]:
    n = len(values)
    if n < 5:
        return values
    k = round(n * ratio)
    return sorted(values)[k : n - k] if n - 2 * k > 0 else values


def _note(klass: VelocityClass, z: float, baseline: float, current: float) -> str:
    return (
        f"{klass.value}: {current:.1f} sales/day vs {baseline:.1f} baseline "
        f"(z={z:+.2f}σ)"
    )
