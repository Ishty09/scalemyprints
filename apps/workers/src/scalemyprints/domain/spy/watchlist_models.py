"""
Watchlist + Alert domain models.

Users follow phrases / shops / listings and get notified when something
worth their attention happens (velocity spike, new listing, price
change, viral signal crossing a POD-readiness threshold).
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WatchType(StrEnum):
    """What the user is watching."""

    PHRASE = "phrase"          # niche/keyword
    SHOP = "shop"              # a specific marketplace shop
    LISTING = "listing"        # a specific listing (by spy_listings.id)
    VIRAL_CATEGORY = "viral_category"  # broad category like "memes"


class AlertChannel(StrEnum):
    """Where alerts are delivered."""

    IN_APP = "in_app"
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class AlertTrigger(StrEnum):
    """What kind of event triggers a notification."""

    VELOCITY_SPIKE = "velocity_spike"
    NEW_LISTING = "new_listing"
    PRICE_DROP = "price_drop"
    PRICE_INCREASE = "price_increase"
    VIRAL_HIT = "viral_hit"          # matching phrase appears in viral feed
    SATURATION_DROP = "saturation_drop"  # niche opens up


class AlertStatus(StrEnum):
    """Lifecycle of a generated alert."""

    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    DISMISSED = "dismissed"
    FAILED = "failed"


class AlertChannelConfig(BaseModel):
    """Per-channel configuration on a Watchlist row."""

    model_config = ConfigDict(frozen=True)

    channel: AlertChannel
    # Channel-specific config — email address, slack webhook, custom POST URL
    target: str | None = Field(default=None, max_length=400)
    enabled: bool = True


class Watchlist(BaseModel):
    """A persisted user watchlist row."""

    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    watch_type: WatchType
    target: str = Field(min_length=1, max_length=400)
    """`target` is the watched value — a phrase, a 'marketplace:handle'
    pair for shops, or a spy_listings.id for listings."""
    label: str | None = Field(default=None, max_length=120)
    triggers: list[AlertTrigger] = Field(default_factory=list)
    channels: list[AlertChannelConfig] = Field(default_factory=list)
    enabled: bool = True
    created_at: datetime
    updated_at: datetime


class Alert(BaseModel):
    """A persisted alert event row."""

    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    watchlist_id: str | None = None
    trigger: AlertTrigger
    status: AlertStatus = AlertStatus.PENDING
    headline: str = Field(min_length=1, max_length=200)
    detail: str | None = Field(default=None, max_length=2000)
    payload: dict[str, object] = Field(default_factory=dict)
    target_url: HttpUrl | None = None
    channels_attempted: list[AlertChannel] = Field(default_factory=list)
    channels_delivered: list[AlertChannel] = Field(default_factory=list)
    severity: Annotated[int, Field(ge=0, le=100)] = 50
    created_at: datetime
    delivered_at: datetime | None = None
    read_at: datetime | None = None


# -----------------------------------------------------------------------------
# Niche suggester
# -----------------------------------------------------------------------------


class NicheSuggestion(BaseModel):
    """One row in the AI niche suggester output."""

    model_config = ConfigDict(frozen=True)

    phrase: str
    opportunity_score: Annotated[int, Field(ge=0, le=100)]
    risk_score: Annotated[int, Field(ge=0, le=100)]
    saturation_score: Annotated[int, Field(ge=0, le=100)]
    pod_readiness_score: Annotated[int, Field(ge=0, le=100)]
    est_monthly_gmv_usd: float = Field(ge=0.0)
    suggested_styles: list[str] = Field(default_factory=list)
    rationale: str
    source: str  # "viral" | "hot_movers" | "tag_mining"
    sample_urls: list[HttpUrl] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Competitor diff
# -----------------------------------------------------------------------------


class CompetitorDiff(BaseModel):
    """Delta between two shop snapshots."""

    model_config = ConfigDict(frozen=True)

    marketplace: str
    handle: str
    previous_at: datetime
    current_at: datetime
    new_listings: list[str] = Field(default_factory=list)        # external_ids
    removed_listings: list[str] = Field(default_factory=list)
    price_changes: list[dict[str, object]] = Field(default_factory=list)
    restock_signals: list[str] = Field(default_factory=list)
    velocity_movers: list[str] = Field(default_factory=list)
    note: str | None = None


# -----------------------------------------------------------------------------
# Seasonality forecaster
# -----------------------------------------------------------------------------


class SeasonalityWindow(BaseModel):
    """Predicted demand window for a niche."""

    model_config = ConfigDict(frozen=True)

    name: str
    starts_at: datetime
    peaks_at: datetime
    ends_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    suggested_drop_by: datetime
    rationale: str
    related_event: str | None = None  # links back to an Event in static_events


class SeasonalityForecast(BaseModel):
    """Output of `seasonality_service.forecast()`."""

    model_config = ConfigDict(frozen=True)

    seed: str
    windows: list[SeasonalityWindow] = Field(default_factory=list)
    horizon_days: int = Field(ge=1, le=730)
    computed_at: datetime


# -----------------------------------------------------------------------------
# Public API keys (for /api/v1/spy/public/*)
# -----------------------------------------------------------------------------


class SpyApiKey(BaseModel):
    """User-owned API key — for programmatic access + webhook export."""

    model_config = ConfigDict(frozen=True)

    id: str
    user_id: str
    label: str = Field(min_length=1, max_length=80)
    prefix: str = Field(min_length=4, max_length=10)
    """The first ~8 chars of the key — safe to display."""
    last_used_at: datetime | None = None
    scopes: list[str] = Field(default_factory=lambda: ["spy:read"])
    revoked: bool = False
    created_at: datetime
