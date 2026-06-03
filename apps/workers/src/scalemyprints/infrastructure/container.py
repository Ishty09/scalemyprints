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
from scalemyprints.domain.spy.enums import Marketplace
from scalemyprints.domain.spy.ports import (
    EmbeddingStore,
    ImageEmbedder,
    ListingStore,
    SpyMarketplaceAdapter,
)
from scalemyprints.domain.spy.reverse_image_service import ReverseImageSearchService
from scalemyprints.domain.spy.search_service import SpySearchService
from scalemyprints.domain.spy.shop_audit_service import ShopAuditService
from scalemyprints.domain.spy.velocity_refresh_service import VelocityRefreshService
from scalemyprints.domain.spy.velocity_service import VelocityAnalyzer as VelocityAnalyzerImpl
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
from scalemyprints.infrastructure.image_search.clip_embedder import (
    CLIPImageEmbedder,
    StubImageEmbedder,
)
from scalemyprints.infrastructure.image_search.memory_store import MemoryEmbeddingStore
from scalemyprints.infrastructure.image_search.pgvector_store import (
    SupabasePgvectorStore,
)
from scalemyprints.infrastructure.ad_libraries.fb_ad_library import (
    FacebookAdLibraryAdapter,
)
from scalemyprints.infrastructure.spy_apis.etsy_spy import EtsySpyAdapter
from scalemyprints.infrastructure.spy_apis.merch_spy import MerchSpyAdapter
from scalemyprints.infrastructure.spy_apis.redbubble_spy import RedbubbleSpyAdapter
from scalemyprints.infrastructure.spy_storage.hot_movers import (
    HotMoversProvider,
    MemoryHotMoversProvider,
    SupabaseHotMoversProvider,
)
from scalemyprints.infrastructure.spy_storage.memory_listing_store import (
    MemoryListingStore,
)
from scalemyprints.infrastructure.spy_storage.supabase_listing_store import (
    SupabaseListingStore,
)
from scalemyprints.infrastructure.llm.niche_expander import OpenAINicheExpander
from scalemyprints.infrastructure.niche_apis.apify_etsy import ApifyEtsyAdapter
from scalemyprints.infrastructure.niche_apis.ebay_browse import EbayBrowseAdapter
from scalemyprints.infrastructure.niche_apis.etsy_public import EtsyPublicSearchAdapter
from scalemyprints.infrastructure.niche_apis.google_trends import GoogleTrendsAdapter
from scalemyprints.infrastructure.niche_apis.marketplace_chain import (
    MarketplaceProviderChain,
)
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

        # ---- Spy ----
        self._spy_adapters: list[SpyMarketplaceAdapter] = self._build_spy_adapters()
        self._spy_listing_store: ListingStore = self._build_spy_listing_store()
        self._spy_embedding_store: EmbeddingStore = self._build_spy_embedding_store()
        self._spy_image_embedder: ImageEmbedder = self._build_spy_image_embedder()
        self._spy_hot_movers: HotMoversProvider = self._build_spy_hot_movers()

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
            spy_storage=self._settings.spy_storage_provider,
            spy_embedder=self._settings.spy_image_embedder,
            spy_adapters=[a.marketplace.value for a in self._spy_adapters],
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
        """
        Marketplace chain — first-success-wins:
          1. eBay Browse API (free OAuth, 5k/day) — usually works
          2. Apify Etsy (paid actor, only if NICHE_MARKETPLACE_PROVIDER=apify
             AND a fresh token; user's free trial expires after 7 days)
          3. Etsy public scrape (Etsy 403/CAPTCHA-blocks datacenter IPs;
             rarely succeeds without a residential proxy, kept as last try)

        Order rationale: eBay first because it's reliable; Apify second
        because user explicitly opted in (and may be paying); Etsy public
        last because it almost never works server-side in 2026.
        """
        providers: list[tuple[str, MarketplaceProvider]] = []

        # 1. eBay Browse — only if credentials configured
        ebay_app = self._settings.ebay_app_id.get_secret_value()
        ebay_cert = self._settings.ebay_cert_id.get_secret_value()
        if ebay_app and ebay_cert:
            try:
                ebay = EbayBrowseAdapter(
                    app_id=ebay_app,
                    cert_id=ebay_cert,
                    environment=self._settings.ebay_environment,
                    http_factory=self._http_factory,
                )
                providers.append(("ebay_browse", ebay))
                logger.info("marketplace_provider_ebay_configured")
            except Exception as e:  # noqa: BLE001
                logger.warning("ebay_browse_init_failed", error=str(e))
        else:
            logger.info("ebay_browse_skipped_no_credentials")

        # 2. Apify Etsy — only when explicitly configured
        provider = self._settings.niche_marketplace_provider.lower()
        apify_token = self._settings.apify_api_token.get_secret_value()
        if provider == "apify" and apify_token:
            providers.append((
                "apify_etsy",
                ApifyEtsyAdapter(
                    api_token=apify_token,
                    actor_id=self._settings.apify_etsy_actor_id,
                ),
            ))
            logger.info("marketplace_provider_apify_configured")

        # 3. Etsy public scrape — last try (now uses curl_cffi browser
        # impersonation; might pass when Etsy temporarily relaxes filters).
        providers.append((
            "etsy_public",
            EtsyPublicSearchAdapter(http_factory=self._http_factory),
        ))

        if len(providers) == 1:
            # Only Etsy public — no chain needed.
            return providers[0][1]

        return MarketplaceProviderChain(providers=providers)

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
    # SPY builders / accessors
    # ------------------------------------------------------------------

    def _build_spy_adapters(self) -> list[SpyMarketplaceAdapter]:
        out: list[SpyMarketplaceAdapter] = []
        proxy = self._settings.spy_proxy_url or None

        if self._settings.spy_etsy_enabled:
            out.append(EtsySpyAdapter(proxy_url=proxy))
        if self._settings.spy_merch_enabled:
            out.append(
                MerchSpyAdapter(
                    apify_token=self._settings.apify_api_token.get_secret_value() or None,
                )
            )
        if self._settings.spy_redbubble_enabled:
            out.append(RedbubbleSpyAdapter(proxy_url=proxy))
        return out

    def _build_spy_listing_store(self) -> ListingStore:
        if self._settings.spy_storage_provider == "memory":
            return MemoryListingStore()
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            logger.warning("spy_listing_store_supabase_creds_missing_falling_back_memory")
            return MemoryListingStore()
        return SupabaseListingStore(supabase_url=url, service_role_key=key)

    def _build_spy_embedding_store(self) -> EmbeddingStore:
        if self._settings.spy_storage_provider == "memory":
            return MemoryEmbeddingStore()
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            logger.warning("spy_embedding_store_supabase_creds_missing_falling_back_memory")
            return MemoryEmbeddingStore()
        return SupabasePgvectorStore(supabase_url=url, service_role_key=key)

    def _build_spy_image_embedder(self) -> ImageEmbedder:
        if self._settings.spy_image_embedder == "stub":
            return StubImageEmbedder()
        return CLIPImageEmbedder(model_name=self._settings.spy_clip_model)

    def _build_spy_hot_movers(self) -> HotMoversProvider:
        if self._settings.spy_storage_provider == "memory":
            return MemoryHotMoversProvider()
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            return MemoryHotMoversProvider()
        return SupabaseHotMoversProvider(supabase_url=url, service_role_key=key)

    @property
    def spy_search_service(self) -> SpySearchService:
        return SpySearchService(
            adapters=self._spy_adapters,
            listing_store=self._spy_listing_store,
        )

    @property
    def spy_reverse_image_service(self) -> ReverseImageSearchService:
        return ReverseImageSearchService(
            embedder=self._spy_image_embedder,
            embedding_store=self._spy_embedding_store,
            listing_store=self._spy_listing_store,
        )

    @property
    def spy_listing_store(self) -> ListingStore:
        return self._spy_listing_store

    @property
    def spy_hot_movers_provider(self) -> HotMoversProvider:
        return self._spy_hot_movers

    # ----- Phase 2 services -----

    @property
    def spy_shop_audit_service(self) -> ShopAuditService:
        return ShopAuditService(adapters=self._spy_adapters)

    @property
    def spy_velocity_refresh_service(self) -> VelocityRefreshService:
        return VelocityRefreshService(
            adapters=self._spy_adapters,
            listing_store=self._spy_listing_store,
            analyzer=VelocityAnalyzerImpl(),
        )

    @property
    def spy_fb_ad_library(self) -> FacebookAdLibraryAdapter:
        return FacebookAdLibraryAdapter(
            proxy_url=self._settings.spy_proxy_url or None,
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
