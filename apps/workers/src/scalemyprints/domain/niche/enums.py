"""
Niche Radar — domain enums.

Top 5 POD markets only. Event categories cover all major demand drivers.
"""

from __future__ import annotations

from enum import StrEnum


class Country(StrEnum):
    """Supported POD markets. 5-country scope by design."""

    US = "US"
    UK = "UK"
    AU = "AU"
    CA = "CA"
    DE = "DE"


class EventCategory(StrEnum):
    """
    Event categories driving POD demand spikes.

    Order roughly reflects POD relevance — holidays drive most listings,
    quirky/awareness less so but still meaningful.
    """

    HOLIDAY = "holiday"            # Christmas, Independence Day, Australia Day
    RELIGIOUS = "religious"        # Easter, Eid, Hanukkah, Diwali
    CULTURAL = "cultural"          # Valentine's, Mother's Day, Black Friday
    SPORTS = "sports"              # Super Bowl, World Cup, Olympics
    AWARENESS = "awareness"        # Pride Month, BCAM, Earth Day
    SEASONAL = "seasonal"          # Back-to-school, summer, winter
    SCHOOL = "school"              # Graduation, Teacher Appreciation
    QUIRKY = "quirky"              # Pi Day, National Dog Day, Star Wars Day


class TrendDirection(StrEnum):
    """How a niche is trending over the analysis window."""

    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"


class CompetitionLevel(StrEnum):
    """Buckets for marketplace saturation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SATURATED = "saturated"


class NicheHealth(StrEnum):
    """Top-line label derived from NHS score."""

    HOT = "hot"          # 75+
    PROMISING = "promising"  # 55-74
    MODERATE = "moderate"    # 40-54
    WEAK = "weak"            # 20-39
    AVOID = "avoid"          # 0-19
