"""
Static events provider — free, fully offline.

Reads a curated JSON of POD-relevant events for 5 countries.
No external API calls. Always available. Fast.

Trade-off: requires manual annual update. We accept this for MVP — events
calendar is reasonably stable (Mother's Day, Christmas, Independence Day
don't move much). For dates that vary (Easter, Mother's Day in some
countries), the curator updates the year tag yearly.

When the user later configures Calendarific, the Container can swap to a
CalendarificProvider — both implement EventsProvider port.
"""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from importlib import resources

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country, EventCategory
from scalemyprints.domain.niche.models import Event

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_events_db() -> list[dict]:
    """Load and cache the static events JSON. Called once per process."""
    try:
        # Use importlib.resources for package data
        with resources.files(
            "scalemyprints.infrastructure.events_data"
        ).joinpath("static_events.json").open("r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("static_events_loaded", count=len(data))
        return data
    except Exception as e:  # noqa: BLE001
        logger.error("static_events_load_failed", error=str(e))
        return []


class StaticEventsProvider:
    """
    Reads events from a curated JSON file.

    Lookups are done in-memory — sub-millisecond response time.
    """

    def __init__(self, *, current_year_anchor: int | None = None) -> None:
        """
        :param current_year_anchor: For testing — pin "now" year. Production
            uses the actual current year derived from event_date arg.
        """
        self._anchor_year = current_year_anchor

    async def list_events(
        self,
        country: Country,
        start_date: date,
        end_date: date,
    ) -> list[Event]:
        """
        Return events for a country between [start_date, end_date].

        Handles year boundaries: if window spans Dec→Jan, both years' events
        are considered.
        """
        raw = _load_events_db()
        results: list[Event] = []

        # Iterate years covered by the window
        for year in range(start_date.year, end_date.year + 1):
            for entry in raw:
                if entry["country"] != country.value:
                    continue
                try:
                    event_date = date(year, entry["month"], entry["day"])
                except ValueError:
                    continue  # Feb 29 in non-leap year etc.
                if not (start_date <= event_date <= end_date):
                    continue

                event = _build_event(entry, event_date, country)
                results.append(event)

        # Sort by date
        results.sort(key=lambda e: e.event_date)
        return results

    async def find_nearest_event(
        self,
        country: Country,
        keyword: str,
        as_of: date,
    ) -> Event | None:
        """
        Find the nearest UPCOMING event whose suggested_niches relate to
        the keyword, OR fall back to the nearest high-relevance event
        regardless of keyword match.

        The 'relate to keyword' match is intentionally loose — we check
        if any suggested niche contains a word from the keyword (or vice
        versa).
        """
        raw = _load_events_db()
        keyword_words = {w for w in keyword.lower().split() if len(w) > 2}

        best_keyword_match: tuple[Event, int] | None = None
        best_general_match: tuple[Event, int] | None = None

        # Look up to 18 months forward
        for year in (as_of.year, as_of.year + 1, as_of.year + 2):
            for entry in raw:
                if entry["country"] != country.value:
                    continue
                try:
                    event_date = date(year, entry["month"], entry["day"])
                except ValueError:
                    continue
                if event_date < as_of:
                    continue
                days_ahead = (event_date - as_of).days
                if days_ahead > 540:  # 18 months
                    break

                event = _build_event(entry, event_date, country)

                # Keyword match check
                niches_text = " ".join(event.suggested_niches).lower()
                event_words = set(niches_text.split()) | set(event.name.lower().split())
                overlap = keyword_words & event_words

                if overlap and event.pod_relevance_score >= 50:
                    if best_keyword_match is None or days_ahead < best_keyword_match[1]:
                        best_keyword_match = (event, days_ahead)

                # Track high-relevance fallback
                if event.pod_relevance_score >= 75:
                    if best_general_match is None or days_ahead < best_general_match[1]:
                        best_general_match = (event, days_ahead)

        if best_keyword_match:
            return best_keyword_match[0]
        if best_general_match:
            return best_general_match[0]
        return None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _build_event(entry: dict, event_date: date, country: Country) -> Event:
    """Convert raw JSON entry → Event domain model."""
    # Re-build canonical id with the resolved year
    iso = event_date.isoformat()
    canonical_name = (
        entry["name"].lower()
        .replace(" ", "-")
        .replace("(", "")
        .replace(")", "")
        .replace(".", "")
        .replace(",", "")
        .replace("/", "-")
    )
    eid = f"{country.value.lower()}-{iso}-{canonical_name}"

    # Parse category safely
    try:
        category = EventCategory(entry["category"])
    except ValueError:
        category = EventCategory.QUIRKY  # safe fallback

    return Event(
        id=eid,
        country=country,
        event_date=event_date,
        name=entry["name"],
        category=category,
        pod_relevance_score=entry["pod_relevance_score"],
        suggested_niches=entry.get("suggested_niches", []),
    )
