"""
Seasonality forecaster.

Given a phrase, return predicted demand windows in the next N days.

Strategy (Phase 4):
1. Pull events from the existing `EventsProvider` (`static_events` by
   default) covering the next `horizon_days` for selected countries.
2. Match each event to the phrase via simple keyword overlap +
   category-tag heuristics (Christmas → christmas, holiday). Score
   match confidence 0-1.
3. For each match, compute the "drop by" date = window start minus
   30 days (typical Etsy SEO indexing lag).

This is a deliberately simple v1 — Phase 5 (if ever) would add
historical sales-curve fitting against the velocity timeseries.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import (
    SeasonalityForecast,
    SeasonalityWindow,
)

if TYPE_CHECKING:
    from scalemyprints.domain.niche.models import Event
    from scalemyprints.domain.niche.ports import EventsProvider

logger = get_logger(__name__)


DEFAULT_LAG_DAYS = 30


class SeasonalityService:
    """Pulls events, matches against phrase, predicts demand windows."""

    def __init__(
        self,
        *,
        events_provider: EventsProvider,
    ) -> None:
        self._events = events_provider

    async def forecast(
        self,
        *,
        seed: str,
        horizon_days: int = 180,
        country: str = "US",
        lag_days: int = DEFAULT_LAG_DAYS,
    ) -> SeasonalityForecast:
        time.monotonic()

        from scalemyprints.domain.niche.enums import Country  # noqa: PLC0415

        try:
            country_enum = Country(country.upper())
        except ValueError:
            country_enum = Country.US

        as_of = datetime.now(UTC).date()
        events = await self._events.upcoming_events(
            country=country_enum,
            as_of=as_of,
            horizon_days=horizon_days,
        )

        seed_tokens = _tokens(seed)
        windows: list[SeasonalityWindow] = []

        for ev in events:
            confidence = _match_event(ev, seed_tokens)
            if confidence < 0.25:
                continue

            window = _build_window(ev, seed, confidence, lag_days)
            if window is not None:
                windows.append(window)

        windows.sort(key=lambda w: w.starts_at)

        return SeasonalityForecast(
            seed=seed,
            windows=windows[:25],
            horizon_days=horizon_days,
            computed_at=datetime.now(UTC),
        )


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    import re  # noqa: PLC0415

    return {t for t in re.split(r"\W+", (text or "").lower()) if len(t) >= 3}


def _match_event(ev: Event, seed_tokens: set[str]) -> float:
    """Return 0.0-1.0 match confidence between a seed and an event."""
    name_tokens = _tokens(ev.name or "")
    desc_tokens = _tokens(getattr(ev, "description", "") or "")
    # Niche `Event` exposes `suggested_niches` rather than free-form tags.
    tag_tokens: set[str] = set()
    for niche in getattr(ev, "suggested_niches", []) or []:
        tag_tokens |= _tokens(niche)

    if not seed_tokens:
        return 0.0

    overlap = (seed_tokens & name_tokens) | (seed_tokens & tag_tokens)
    if overlap:
        # Name/tag hit is high-confidence
        return min(1.0, 0.5 + 0.5 * len(overlap) / max(1, len(seed_tokens)))

    if seed_tokens & desc_tokens:
        return 0.3

    return 0.0


def _build_window(
    ev: Event,
    seed: str,
    confidence: float,
    lag_days: int,
) -> SeasonalityWindow | None:
    try:
        event_dt = datetime.combine(ev.event_date, datetime.min.time(), tzinfo=UTC)
    except Exception:
        return None

    # Standard POD demand window: starts 6 weeks before, peaks ~1 week
    # before, fades 1 week after.
    starts = event_dt - timedelta(days=42)
    peaks = event_dt - timedelta(days=7)
    ends = event_dt + timedelta(days=7)
    drop_by = starts - timedelta(days=lag_days)

    return SeasonalityWindow(
        name=ev.name,
        starts_at=starts,
        peaks_at=peaks,
        ends_at=ends,
        confidence=round(confidence, 3),
        suggested_drop_by=drop_by,
        rationale=(
            f'"{seed}" matches "{ev.name}" '
            f"(confidence={confidence:.2f}). Drop designs by "
            f"{drop_by.date().isoformat()} for SEO indexing lag of {lag_days}d."
        ),
        related_event=ev.name,
    )
