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
from scalemyprints.domain.design.enums import ImageGenProviderName
from scalemyprints.domain.design.generation_service import DesignGenerationService
from scalemyprints.domain.design.ports import (
    DesignJobStore,
    DesignStorage,
    ImageGenProvider,
    PromptEnricher,
    QuotaService,
)
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
from scalemyprints.infrastructure.image_gen.disabled import DisabledImageGenProvider
from scalemyprints.infrastructure.image_gen.falai import FalFluxAdapter
from scalemyprints.infrastructure.image_gen.openai_dalle import OpenAIDalleAdapter
from scalemyprints.infrastructure.image_gen.provider_chain import ImageGenProviderChain
from scalemyprints.infrastructure.job_store.memory_job_store import (
    MemoryDesignJobStore,
)
from scalemyprints.infrastructure.job_store.supabase_job_store import (
    SupabaseDesignJobStore,
)
from scalemyprints.infrastructure.llm.design_prompt_enricher import (
    OpenAIDesignPromptEnricher,
    TemplateOnlyDesignPromptEnricher,
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
from scalemyprints.infrastructure.quota.plan_resolver import StaticPlanResolver
from scalemyprints.infrastructure.quota.supabase_quota import (
    MemoryDesignQuota,
    SupabaseDesignQuota,
)
from scalemyprints.infrastructure.storage.memory_storage import MemoryDesignStorage
from scalemyprints.infrastructure.storage.supabase_storage import SupabaseDesignStorage
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

        # ---- Design Engine ----
        self._design_provider_name = ""
        self._design_image_gen: ImageGenProvider = self._build_design_image_gen()
        self._design_enricher: PromptEnricher = self._build_design_enricher()
        self._design_storage: DesignStorage = self._build_design_storage()
        self._design_job_store: DesignJobStore = self._build_design_job_store()
        self._design_quota: QuotaService = self._build_design_quota()

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
            design_image_gen=self._design_provider_name,
            design_storage=self._settings.design_storage_provider,
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
                except Exception as e:
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
        except Exception as e:
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
            except Exception as e:
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
    # DESIGN ENGINE builders / accessors
    # ------------------------------------------------------------------

    def _build_design_image_gen(self) -> ImageGenProvider:
        """
        Image-gen chain (first-success-wins):
          • IMAGE_GEN_PROVIDER=disabled            → disabled stub
          • IMAGE_GEN_PROVIDER=falai_free|falai_paid → Fal only
          • IMAGE_GEN_PROVIDER=openai_dalle3       → OpenAI only
          • IMAGE_GEN_PROVIDER=auto_chain (default) → Fal → DALL-E → disabled
        """
        provider_setting = self._settings.image_gen_provider

        def _fal(provider_enum: ImageGenProviderName) -> ImageGenProvider | None:
            key = self._settings.fal_api_key.get_secret_value()
            if not key:
                return None
            return FalFluxAdapter(
                api_key=key,
                provider=provider_enum,
                http_factory=self._http_factory,
            )

        def _dalle() -> ImageGenProvider | None:
            if not self._settings.openai_image_gen_enabled:
                return None
            key = self._settings.openai_api_key.get_secret_value()
            if not key:
                return None
            return OpenAIDalleAdapter(
                api_key=key,
                http_factory=self._http_factory,
            )

        if provider_setting == "disabled":
            self._design_provider_name = "disabled"
            return DisabledImageGenProvider()

        if provider_setting in ("falai_free", "falai_paid"):
            chosen = (
                ImageGenProviderName.FAL_FLUX_PRO
                if provider_setting == "falai_paid"
                else ImageGenProviderName.FAL_FLUX_SCHNELL
            )
            adapter = _fal(chosen)
            if adapter is None:
                logger.warning("design_falai_no_key_falling_back_disabled")
                self._design_provider_name = "disabled"
                return DisabledImageGenProvider()
            self._design_provider_name = chosen.value
            return adapter

        if provider_setting == "openai_dalle3":
            adapter = _dalle()
            if adapter is None:
                logger.warning("design_dalle_no_key_falling_back_disabled")
                self._design_provider_name = "disabled"
                return DisabledImageGenProvider()
            self._design_provider_name = ImageGenProviderName.OPENAI_DALLE3.value
            return adapter

        # auto_chain — try Fal Schnell, fall through to DALL-E.
        chain: list[tuple[str, ImageGenProvider]] = []
        fal = _fal(ImageGenProviderName(self._settings.fal_default_provider))
        if fal is not None:
            chain.append((fal.provider_name.value, fal))
        dalle = _dalle()
        if dalle is not None:
            chain.append((dalle.provider_name.value, dalle))
        if not chain:
            logger.warning("design_no_image_gen_keys_disabled")
            self._design_provider_name = "disabled"
            return DisabledImageGenProvider()
        self._design_provider_name = "+".join(name for name, _ in chain)
        return ImageGenProviderChain(providers=chain)

    def _build_design_enricher(self) -> PromptEnricher:
        key = self._settings.openai_api_key.get_secret_value()
        if not key:
            return TemplateOnlyDesignPromptEnricher()
        return OpenAIDesignPromptEnricher(
            api_key=key,
            model=self._settings.openai_model_cheap,
        )

    def _build_design_storage(self) -> DesignStorage:
        if self._settings.design_storage_provider == "memory":
            logger.info("design_storage_memory_mode")
            return MemoryDesignStorage()
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            logger.warning("design_storage_supabase_creds_missing_falling_back_memory")
            return MemoryDesignStorage()
        return SupabaseDesignStorage(
            supabase_url=url,
            service_role_key=key,
            bucket=self._settings.design_storage_bucket,
        )

    def _build_design_job_store(self) -> DesignJobStore:
        if self._settings.design_storage_provider == "memory":
            return MemoryDesignJobStore()
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            logger.warning("design_job_store_supabase_creds_missing_falling_back_memory")
            return MemoryDesignJobStore()
        return SupabaseDesignJobStore(supabase_url=url, service_role_key=key)

    def _build_design_quota(self) -> QuotaService:
        if self._settings.design_storage_provider == "memory":
            return MemoryDesignQuota(
                plan_resolver=StaticPlanResolver(
                    default_plan=self._settings.design_default_plan
                ),
            )
        url = self._settings.supabase_url
        key = self._settings.supabase_service_role_key.get_secret_value()
        if not url or not key:
            logger.warning("design_quota_supabase_creds_missing_falling_back_memory")
            return MemoryDesignQuota(
                plan_resolver=StaticPlanResolver(
                    default_plan=self._settings.design_default_plan
                ),
            )
        return SupabaseDesignQuota(
            supabase_url=url,
            service_role_key=key,
        )

    @property
    def design_image_gen(self) -> ImageGenProvider:
        return self._design_image_gen

    @property
    def design_job_store(self) -> DesignJobStore:
        return self._design_job_store

    @property
    def design_quota(self) -> QuotaService:
        return self._design_quota

    @property
    def design_storage(self) -> DesignStorage:
        return self._design_storage

    def build_design_generation_service(self) -> DesignGenerationService:
        return DesignGenerationService(
            prompt_enricher=self._design_enricher,
            image_gen_provider=self._design_image_gen,
            storage=self._design_storage,
            job_store=self._design_job_store,
            quota=self._design_quota,
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
                except Exception:
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
                except Exception:
                    logger.warning(
                        "trademark_adapter_close_failed",
                        adapter=type(adapter).__name__,
                    )
        for client in (self._niche_marketplace, self._niche_trends):
            close_method = getattr(client, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:
                    logger.warning(
                        "niche_client_close_failed",
                        client=type(client).__name__,
                    )
        for design_dep in (
            self._design_image_gen,
            self._design_storage,
        ):
            close_method = getattr(design_dep, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:
                    logger.warning(
                        "design_dep_close_failed",
                        component=type(design_dep).__name__,
                    )
        logger.info("service_container_closed")


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    return ServiceContainer(settings=get_settings())
