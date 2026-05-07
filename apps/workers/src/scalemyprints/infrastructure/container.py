"""
Service composition root.

Provider chains:
- US:  USPTO (if key) → Marker → Markbase
- EU:  EUIPO Official (OAuth2) → TMView → EUIPO legacy
- UK:  UKIPO → TMView (if jurisdiction matches)
- AU:  IP Australia (only option)

Each chain is wrapped in circuit breakers so a flapping provider is
short-circuited automatically.
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
from scalemyprints.infrastructure.niche_apis.trends_chain import TrendsProviderChain
from scalemyprints.infrastructure.niche_apis.wikipedia_trends import (
    WikipediaTrendsAdapter,
)
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory
from scalemyprints.infrastructure.trademark_apis.euipo import EUIPOClient
from scalemyprints.infrastructure.trademark_apis.euipo_official import (
    EUIPOOfficialClient,
)
from scalemyprints.infrastructure.trademark_apis.ipau import IPAustraliaClient
from scalemyprints.infrastructure.trademark_apis.markbase import MarkbaseClient
from scalemyprints.infrastructure.trademark_apis.marker import MarkerAPIClient
from scalemyprints.infrastructure.trademark_apis.provider_chain import (
    TrademarkProviderChain,
)
from scalemyprints.infrastructure.trademark_apis.tmview import TMViewClient
from scalemyprints.infrastructure.trademark_apis.tmview_uk import TMViewUKClient
from scalemyprints.infrastructure.trademark_apis.ukipo import UKIPOClient
from scalemyprints.infrastructure.trademark_apis.uspto import USPTOClient

logger = get_logger(__name__)


class ServiceContainer:
    """Owns shared infrastructure resources and hands out wired services."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._http_factory = HttpClientFactory()

        self._cache: CacheStore = self._build_cache()
        self._common_law: CommonLawChecker = self._build_common_law()

        self._us_provider_name = ""
        self._eu_provider_name = ""
        self._uk_provider_name = ""

        # Underlying single-adapter clients owned for shutdown.
        self._owned_trademark_clients: list[TrademarkAPI] = []

        self._us_client: TrademarkAPI = self._build_us_client()
        self._eu_client: TrademarkAPI = self._build_eu_client()
        self._uk_client: TrademarkAPI = self._build_uk_client()
        self._au_client: TrademarkAPI = IPAustraliaClient(
            base_url=self._settings.ipau_api_base_url,
            http_factory=self._http_factory,
        )

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
            uk_provider=self._uk_provider_name,
            niche_trends=self._settings.niche_trends_provider,
            niche_marketplace=self._settings.niche_marketplace_provider,
            niche_events=self._settings.niche_events_provider,
            niche_llm=self._settings.niche_llm_provider,
            environment=self._settings.environment.value,
        )

    # ------------------------------------------------------------------
    # TRADEMARK chains
    # ------------------------------------------------------------------

    def _build_us_client(self) -> TrademarkAPI:
        """US chain: USPTO (if key) → Marker → Markbase."""
        providers: list[tuple[str, TrademarkAPI]] = []

        uspto_key = self._settings.uspto_api_key.get_secret_value()
        if uspto_key:
            uspto = USPTOClient(
                base_url=self._settings.uspto_api_base_url,
                http_factory=self._http_factory,
            )
            self._owned_trademark_clients.append(uspto)
            providers.append(("uspto", uspto))

        marker_user = self._settings.marker_api_username.get_secret_value() or None
        marker_pass = self._settings.marker_api_password.get_secret_value() or None
        marker = MarkerAPIClient(
            base_url=self._settings.marker_api_base_url,
            username=marker_user,
            password=marker_pass,
            http_factory=self._http_factory,
        )
        self._owned_trademark_clients.append(marker)
        providers.append(("marker", marker))

        markbase = MarkbaseClient(http_factory=self._http_factory)
        self._owned_trademark_clients.append(markbase)
        providers.append(("markbase", markbase))

        self._us_provider_name = "+".join(name for name, _ in providers)

        return TrademarkProviderChain(
            jurisdiction=JurisdictionCode.US,
            providers=providers,
        )

    def _build_eu_client(self) -> TrademarkAPI:
        """
        EU chain (first success wins):
          1. EUIPO Official (OAuth2) — authoritative; if credentials configured
          2. TMView                  — public WIPO/EUIPO joint
          3. EUIPO legacy            — last-resort fallback
        """
        providers: list[tuple[str, TrademarkAPI]] = []

        # 1. EUIPO Official OAuth2
        if self._settings.euipo_official_enabled:
            tm_id = self._settings.euipo_tm_client_id.get_secret_value()
            tm_secret = self._settings.euipo_tm_client_secret.get_secret_value()
            if tm_id and tm_secret:
                try:
                    euipo_official = EUIPOOfficialClient(
                        client_id=tm_id,
                        client_secret=tm_secret,
                        token_url=self._settings.euipo_tm_token_url,
                        api_base_url=self._settings.euipo_tm_api_base_url,
                        scope=self._settings.euipo_tm_scope,
                        http_factory=self._http_factory,
                    )
                    self._owned_trademark_clients.append(euipo_official)
                    providers.append(("euipo_official", euipo_official))
                except Exception as e:  # noqa: BLE001
                    logger.warning(
                        "euipo_official_init_failed",
                        error=str(e),
                    )
            else:
                logger.info(
                    "euipo_official_skipped_no_credentials",
                )

        # 2. TMView
        tmview = TMViewClient(
            base_url=self._settings.tmview_api_base_url,
            http_factory=self._http_factory,
        )
        self._owned_trademark_clients.append(tmview)
        providers.append(("tmview", tmview))

        # 3. EUIPO legacy
        euipo_legacy = EUIPOClient(
            base_url=self._settings.euipo_api_base_url,
            http_factory=self._http_factory,
        )
        self._owned_trademark_clients.append(euipo_legacy)
        providers.append(("euipo_legacy", euipo_legacy))

        self._eu_provider_name = "+".join(name for name, _ in providers)

        return TrademarkProviderChain(
            jurisdiction=JurisdictionCode.EU,
            providers=providers,
        )

    def _build_uk_client(self) -> TrademarkAPI:
        """
        UK chain: UKIPO → TMViewUK (first success wins).

        Both UKIPO (Cloudflare WAF) and tmdn.org (Akamai) block datacenter
        IPs based primarily on TLS JA3 fingerprint. UKIPOClient and
        TMViewUKClient now use curl_cffi to mimic real Chrome's handshake,
        which bypasses fingerprint-based detection. If the upstream STILL
        blocks (e.g. UKIPO's Cloudflare WAF on pure ASN), the chain falls
        through to the coverage-limited stub.

        Set UK_PROXY_URL to layer in residential IPs as well.
        """
        proxy_url = self._settings.uk_effective_proxy_url or None

        if proxy_url:
            uk_factory = HttpClientFactory(proxy_url=proxy_url)
            logger.info("uk_chain_using_proxy_plus_browser_impersonation")
        else:
            uk_factory = HttpClientFactory()
            logger.info("uk_chain_using_browser_impersonation_only")

        ukipo = UKIPOClient(
            base_url=self._settings.ukipo_api_base_url,
            http_factory=uk_factory,
        )
        self._owned_trademark_clients.append(ukipo)

        providers: list[tuple[str, TrademarkAPI]] = [("ukipo", ukipo)]

        try:
            tmview_uk = TMViewUKClient(
                base_url=self._settings.tmview_api_base_url,
                http_factory=uk_factory,
            )
            if tmview_uk.jurisdiction == JurisdictionCode.UK:
                self._owned_trademark_clients.append(tmview_uk)
                providers.append(("tmview_uk", tmview_uk))
            else:
                logger.debug(
                    "tmview_uk_fallback_unavailable",
                    actual_jurisdiction=tmview_uk.jurisdiction.value,
                )
        except Exception as e:  # noqa: BLE001
            logger.warning("tmview_uk_fallback_init_failed", error=str(e))

        self._uk_provider_name = "+".join(name for name, _ in providers)

        return TrademarkProviderChain(
            jurisdiction=JurisdictionCode.UK,
            providers=providers,
        )

    # ------------------------------------------------------------------
    # NICHE / misc builders
    # ------------------------------------------------------------------

    def _build_cache(self) -> CacheStore:
        return MemoryCache()

    def _build_common_law(self) -> CommonLawChecker:
        return NoOpCommonLawChecker()

    def _build_niche_trends(self) -> TrendsProvider:
        """
        Trends chain: Wikipedia (primary, reliable from datacenter) →
        Google Trends (richer signal when not 429-blocked).

        Wikipedia Pageviews API is the only public free trends-style
        signal that consistently works from datacenter IPs in 2026.
        Google Trends is kept in the chain for the rare case it
        returns data — the chain skips it on 429.
        """
        wikipedia = WikipediaTrendsAdapter(http_factory=self._http_factory)
        google = GoogleTrendsAdapter()
        return TrendsProviderChain(
            providers=[
                ("wikipedia", wikipedia),
                ("google_trends", google),
            ],
        )

    def _build_niche_marketplace(self) -> MarketplaceProvider:
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
        return TrademarkSearchService(
            trademark_apis=self.trademark_apis,
            cache=self._cache,
            common_law_checker=self._common_law,
        )

    @property
    def niche_events_provider(self) -> EventsProvider:
        return self._niche_events

    @property
    def niche_expander(self) -> NicheExpander | None:
        return self._niche_expander

    def build_niche_search_service(self) -> NicheSearchService:
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
        wrappers = (
            self._us_client,
            self._eu_client,
            self._uk_client,
            self._au_client,
        )
        for client in wrappers:
            close_method = getattr(client, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "trademark_client_close_failed",
                        client=type(client).__name__,
                    )
        for adapter in self._owned_trademark_clients:
            if adapter in wrappers:
                continue
            close_method = getattr(adapter, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "trademark_adapter_close_failed",
                        adapter=type(adapter).__name__,
                    )
        for client in (self._niche_marketplace, self._niche_trends):
            close_method = getattr(client, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "niche_client_close_failed",
                        client=type(client).__name__,
                    )
        logger.info("service_container_closed")


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer(settings=get_settings())
