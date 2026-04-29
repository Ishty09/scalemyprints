"""
Service composition root.

The ONE place where domain services are wired up with their infrastructure
adapters. Every other part of the codebase receives fully-constructed
services, not raw adapters.

Provider selection happens here:
- US:  Marker API (default) → USPTO direct (when api key configured)
- EU:  TMview (default) → EUIPO direct (legacy, deprecated)
- UK:  UKIPO (only option)
- AU:  IP Australia (only option)

Swapping providers (memory cache → Redis, disabled common-law → real) is
done here based on settings. The rest of the code doesn't know.
"""

from __future__ import annotations

from functools import lru_cache

from scalemyprints.core.config import Settings, get_settings
from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.ports import (
    EventsProvider,
    MarketplaceProvider,
    NicheCacheStore,
    NicheExpander,
    TrendsProvider,
)
from scalemyprints.domain.niche.search_service import NicheSearchService
from scalemyprints.domain.trademark.enums import JurisdictionCode
from scalemyprints.domain.trademark.ports import (
    CacheStore,
    CommonLawChecker,
    TrademarkAPI,
)
from scalemyprints.domain.trademark.search_service import TrademarkSearchService
from scalemyprints.infrastructure.cache.memory import MemoryCache
from scalemyprints.infrastructure.cache.niche_memory import NicheMemoryCache
from scalemyprints.infrastructure.common_law.no_op import NoOpCommonLawChecker
from scalemyprints.infrastructure.llm.niche_expander import OpenAINicheExpander
from scalemyprints.infrastructure.niche_apis.apify_etsy import ApifyEtsyAdapter
from scalemyprints.infrastructure.niche_apis.etsy_public import EtsyPublicSearchAdapter
from scalemyprints.infrastructure.niche_apis.google_trends import GoogleTrendsAdapter
from scalemyprints.infrastructure.niche_apis.static_events import StaticEventsProvider
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory
from scalemyprints.infrastructure.trademark_apis.euipo import EUIPOClient
from scalemyprints.infrastructure.trademark_apis.ipau import IPAustraliaClient
from scalemyprints.infrastructure.trademark_apis.marker import MarkerAPIClient
from scalemyprints.infrastructure.trademark_apis.tmview import TMViewClient
from scalemyprints.infrastructure.trademark_apis.ukipo import UKIPOClient
from scalemyprints.infrastructure.trademark_apis.uspto import USPTOClient

logger = get_logger(__name__)


class ServiceContainer:
    """
    Container that owns the lifecycle of shared infrastructure resources
    (HTTP clients, cache) and hands out fully-wired domain services.

    One container per process. Usually accessed via `get_container()`.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http_factory = HttpClientFactory()

        # Single shared cache instance (process-local)
        self._cache: CacheStore = self._build_cache()

        # Single shared common-law checker
        self._common_law: CommonLawChecker = self._build_common_law()

        # Trademark API clients — provider-selected
        self._us_provider_name = "marker"  # default; updated by _build_us_client
        self._eu_provider_name = "tmview"  # default; updated by _build_eu_client
        self._us_client: TrademarkAPI = self._build_us_client()
        self._eu_client: TrademarkAPI = self._build_eu_client()
        self._uk_client: TrademarkAPI = UKIPOClient(
            base_url=self._settings.ukipo_api_base_url,
            http_factory=self._http_factory,
        )
        self._au_client: TrademarkAPI = IPAustraliaClient(
            base_url=self._settings.ipau_api_base_url,
            http_factory=self._http_factory,
        )

        # Niche Radar services
        self._niche_cache: NicheCacheStore = NicheMemoryCache()
        self._niche_trends: TrendsProvider = self._build_niche_trends()
        self._niche_marketplace: MarketplaceProvider = self._build_niche_marketplace()
        self._niche_events: EventsProvider = self._build_niche_events()
        self._niche_expander: NicheExpander | None = self._build_niche_expander()

        logger.info(
            "service_container_initialized",
            cache_provider=self._settings.cache_provider,
            common_law_provider="noop",
            us_provider=self._us_provider_name,
            eu_provider=self._eu_provider_name,
            niche_trends=self._settings.niche_trends_provider,
            niche_marketplace=self._settings.niche_marketplace_provider,
            niche_events=self._settings.niche_events_provider,
            niche_llm=self._settings.niche_llm_provider,
            environment=self._settings.environment.value,
        )

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    def _build_us_client(self) -> TrademarkAPI:
        """
        Pick the US trademark provider based on settings.

        - "uspto" → USPTOClient (requires USPTO API key — usually only when
                                  explicitly configured)
        - "marker" → MarkerAPIClient (default; works without USPTO key)

        If "uspto" is selected but no API key is set, we fall back to Marker
        rather than fail — this avoids hard breakage when keys go missing.
        """
        provider = self._settings.us_trademark_provider.lower()

        if provider == "uspto":
            api_key = self._settings.uspto_api_key.get_secret_value()
            if api_key:
                self._us_provider_name = "uspto"
                return USPTOClient(
                    base_url=self._settings.uspto_api_base_url,
                    http_factory=self._http_factory,
                )
            logger.warning(
                "uspto_provider_selected_but_no_key_falling_back_to_marker"
            )

        # Default: Marker API
        self._us_provider_name = "marker"
        marker_user = self._settings.marker_api_username.get_secret_value() or None
        marker_pass = self._settings.marker_api_password.get_secret_value() or None
        return MarkerAPIClient(
            base_url=self._settings.marker_api_base_url,
            username=marker_user,
            password=marker_pass,
            http_factory=self._http_factory,
        )

    def _build_eu_client(self) -> TrademarkAPI:
        """
        Pick the EU trademark provider based on settings.

        - "tmview" → TMViewClient (default; WIPO/EUIPO joint, public)
        - "euipo" → EUIPOClient (legacy direct EUIPO endpoint, less reliable)
        """
        provider = self._settings.eu_trademark_provider.lower()

        if provider == "euipo":
            self._eu_provider_name = "euipo"
            return EUIPOClient(
                base_url=self._settings.euipo_api_base_url,
                http_factory=self._http_factory,
            )

        # Default: TMview
        self._eu_provider_name = "tmview"
        return TMViewClient(
            base_url=self._settings.tmview_api_base_url,
            http_factory=self._http_factory,
        )

    # ------------------------------------------------------------------
    # Factory methods for builders
    # ------------------------------------------------------------------

    def _build_cache(self) -> CacheStore:
        # Phase A: always memory. Phase B+: branch on settings.cache_provider.
        return MemoryCache()

    def _build_common_law(self) -> CommonLawChecker:
        # Phase A: no-op. Phase B+: return real EtsyCommonLawChecker.
        return NoOpCommonLawChecker()

    def _build_niche_trends(self) -> TrendsProvider:
        # Only "google" implemented for free tier; future: paid alternates
        return GoogleTrendsAdapter()

    def _build_niche_marketplace(self) -> MarketplaceProvider:
        """
        Choose the marketplace provider based on configuration.

        Selection logic:
        1. If `niche_marketplace_provider` is explicitly "apify" AND token exists
           → use Apify (paid, residential proxies, reliable from any IP)
        2. If "etsy_public" or anything else → use the free Etsy scraper

        Auto-promotion: if the provider setting is left at the default
        ("etsy_public") but an APIFY_API_TOKEN is present, we DO NOT silently
        switch — that would be surprising. The user must opt in by setting
        NICHE_MARKETPLACE_PROVIDER=apify.
        """
        provider = self._settings.niche_marketplace_provider.lower()
        apify_token = self._settings.apify_api_token.get_secret_value()

        if provider == "apify":
            if not apify_token:
                logger.warning(
                    "apify_provider_selected_but_token_missing",
                    fallback="etsy_public",
                )
                return EtsyPublicSearchAdapter(http_factory=self._http_factory)
            logger.info(
                "marketplace_provider_apify",
                actor=self._settings.apify_etsy_actor_id,
            )
            return ApifyEtsyAdapter(
                api_token=apify_token,
                actor_id=self._settings.apify_etsy_actor_id,
            )

        # Default: free Etsy public scraper
        return EtsyPublicSearchAdapter(http_factory=self._http_factory)

    def _build_niche_events(self) -> EventsProvider:
        provider = self._settings.niche_events_provider.lower()
        if provider == "calendarific" and self._settings.calendarific_api_key.get_secret_value():
            logger.info("calendarific_configured_but_adapter_pending_use_static")
        return StaticEventsProvider()

    def _build_niche_expander(self) -> NicheExpander | None:
        provider = self._settings.niche_llm_provider.lower()
        if provider == "disabled":
            return None
        api_key = self._settings.openai_api_key.get_secret_value()
        if not api_key:
            logger.info("niche_expander_disabled_no_openai_key")
            return None
        return OpenAINicheExpander(api_key=api_key)

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    @property
    def cache(self) -> CacheStore:
        return self._cache

    @property
    def common_law_checker(self) -> CommonLawChecker:
        return self._common_law

    @property
    def trademark_apis(self) -> dict[JurisdictionCode, TrademarkAPI]:
        return {
            JurisdictionCode.US: self._us_client,
            JurisdictionCode.EU: self._eu_client,
            JurisdictionCode.UK: self._uk_client,
            JurisdictionCode.AU: self._au_client,
        }

    def build_trademark_search_service(self) -> TrademarkSearchService:
        """
        Instantiate the trademark search orchestrator with all adapters.

        Cheap to call — all infrastructure is already built.
        """
        return TrademarkSearchService(
            trademark_apis=self.trademark_apis,
            cache=self._cache,
            common_law_checker=self._common_law,
        )

    # ------------------------------------------------------------------
    # Niche Radar accessors
    # ------------------------------------------------------------------

    @property
    def niche_events_provider(self) -> EventsProvider:
        return self._niche_events

    @property
    def niche_expander(self) -> NicheExpander | None:
        return self._niche_expander

    def build_niche_search_service(self) -> NicheSearchService:
        """Instantiate the niche search orchestrator."""
        return NicheSearchService(
            trends_provider=self._niche_trends,
            marketplace_provider=self._niche_marketplace,
            events_provider=self._niche_events,
            cache=self._niche_cache,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Release HTTP clients and other resources at shutdown."""
        # Trademark clients
        for client in (self._us_client, self._eu_client, self._uk_client, self._au_client):
            close_method = getattr(client, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "trademark_client_close_failed", client=type(client).__name__
                    )
        # Niche clients (some may not own HTTP)
        for client in (self._niche_marketplace,):
            close_method = getattr(client, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "niche_client_close_failed", client=type(client).__name__
                    )
        logger.info("service_container_closed")


# -----------------------------------------------------------------------------
# Process-wide singleton
# -----------------------------------------------------------------------------


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    """
    Get the process-wide ServiceContainer.

    First call constructs; subsequent calls return the cached instance.
    For tests that need isolation, call `get_container.cache_clear()`.
    """
    return ServiceContainer(settings=get_settings())
