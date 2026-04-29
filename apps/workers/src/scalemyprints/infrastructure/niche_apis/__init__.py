"""Niche Radar infrastructure adapters."""

from scalemyprints.infrastructure.niche_apis.apify_etsy import ApifyEtsyAdapter
from scalemyprints.infrastructure.niche_apis.etsy_public import EtsyPublicSearchAdapter
from scalemyprints.infrastructure.niche_apis.google_trends import GoogleTrendsAdapter
from scalemyprints.infrastructure.niche_apis.static_events import StaticEventsProvider

__all__ = [
    "ApifyEtsyAdapter",
    "EtsyPublicSearchAdapter",
    "GoogleTrendsAdapter",
    "StaticEventsProvider",
]
