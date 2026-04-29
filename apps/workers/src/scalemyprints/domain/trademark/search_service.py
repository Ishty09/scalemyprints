"""
Trademark search orchestrator.

Composes pure domain services (scorer, genericness, recommender) with
injected ports (TrademarkAPI, CacheStore, CommonLawChecker) to produce a
complete search response.

Lives in the domain layer but orchestrates across services — the only class
in the domain that composes others. Still zero I/O of its own; all I/O goes
through injected ports.

Design:
- Ports injected via constructor (dependency injection)
- Parallel API calls via asyncio.gather (I/O concurrency)
- Cache read-through with stale-on-error fallback
- Graceful degradation: if one jurisdiction fails, others still score
- All outputs validated via Pydantic
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass

import orjson

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.shared.clock import Clock, SystemClock
from scalemyprints.domain.trademark.enums import JurisdictionCode, score_to_risk_level
from scalemyprints.domain.trademark.genericness import GenericnessCalculator
from scalemyprints.domain.trademark.models import (
    JurisdictionRisk,
    TrademarkSearchRequest,
    TrademarkSearchResponse,
)
from scalemyprints.domain.trademark.ports import (
    CacheStore,
    CommonLawChecker,
    TrademarkAPI,
    TrademarkSearchResult,
)
from scalemyprints.domain.trademark.recommender import RecommendationGenerator
from scalemyprints.domain.trademark.scorer import RiskScorer

logger = get_logger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours
CACHE_KEY_PREFIX = "tm:search:v1"


@dataclass(frozen=True, slots=True)
class SearchServiceConfig:
    """Runtime configuration for the search service."""

    cache_enabled: bool = True
    common_law_enabled_default: bool = True
    # Parallel timeout — if a jurisdiction takes longer than this, treat as failed
    per_jurisdiction_timeout_seconds: float = 15.0
    common_law_timeout_seconds: float = 10.0


class TrademarkSearchService:
    """
    Orchestrates a trademark search across multiple jurisdictions.

    Responsibilities:
    1. Check cache (fast path)
    2. Fan out to jurisdiction APIs in parallel
    3. Estimate common-law use
    4. Compute genericness
    5. Score each jurisdiction
    6. Compute overall risk
    7. Generate recommendations
    8. Cache result
    9. Return validated response
    """

    def __init__(
        self,
        *,
        trademark_apis: dict[JurisdictionCode, TrademarkAPI],
        cache: CacheStore | None = None,
        common_law_checker: CommonLawChecker | None = None,
        scorer: RiskScorer | None = None,
        genericness_calculator: GenericnessCalculator | None = None,
        recommendation_generator: RecommendationGenerator | None = None,
        clock: Clock | None = None,
        config: SearchServiceConfig | None = None,
    ) -> None:
        if not trademark_apis:
            raise ValueError("At least one TrademarkAPI must be provided")

        self._apis = trademark_apis
        self._cache = cache
        self._common_law = common_law_checker
        self._scorer = scorer or RiskScorer()
        self._genericness = genericness_calculator or GenericnessCalculator()
        self._recommender = recommendation_generator or RecommendationGenerator()
        self._clock = clock or SystemClock()
        self._config = config or SearchServiceConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search(self, request: TrademarkSearchRequest) -> TrademarkSearchResponse:
        """
        Execute a full trademark search.

        Always returns a validated response. Partial failures (e.g., one
        jurisdiction API down) are surfaced in per-jurisdiction `error`
        fields and in recommendations, not raised.
        """
        started_at = self._clock.now()
        log = logger.bind(
            phrase=request.phrase,
            jurisdictions=[j.value for j in request.jurisdictions],
            nice_classes=request.nice_classes,
        )
        log.info("trademark_search_start")

        # 1. Cache lookup
        cache_key = self._build_cache_key(request)
        if self._config.cache_enabled and self._cache:
            cached = await self._try_cache_get(cache_key)
            if cached is not None:
                log.info("trademark_search_cache_hit")
                return cached

        # 2. Parallel fan-out
        jurisdiction_results, common_law_density = await self._fan_out(request)

        # 3. Compute genericness (pure, sync, fast)
        genericness = self._genericness.calculate(request.phrase)

        # 4. Score each jurisdiction
        jurisdiction_risks = self._score_all(
            request=request,
            results=jurisdiction_results,
            common_law_density=common_law_density,
            genericness=genericness,
        )

        # 5. Compute overall
        overall_score, _had_errors = self._scorer.score_overall(
            jurisdiction_risks=jurisdiction_risks,
            user_selling_in=request.jurisdictions,
        )
        overall_level = score_to_risk_level(overall_score)

        # 6. Generate recommendations
        recommendations = self._recommender.generate(
            jurisdiction_risks=jurisdiction_risks,
            user_selling_in=request.jurisdictions,
        )

        # 7. Build response
        finished_at = self._clock.now()
        duration_ms = int((finished_at - started_at).total_seconds() * 1000)

        response = TrademarkSearchResponse(
            phrase=request.phrase,
            overall_risk_score=overall_score,
            overall_risk_level=overall_level,
            jurisdictions=jurisdiction_risks,
            recommendations=recommendations,
            phrase_genericness=genericness,
            nice_classes_searched=request.nice_classes,
            analyzed_at=finished_at,
            from_cache=False,
            duration_ms=duration_ms,
        )

        # 8. Cache write (fire-and-forget to not block response)
        if self._config.cache_enabled and self._cache:
            await self._try_cache_set(cache_key, response)

        log.info(
            "trademark_search_complete",
            overall_score=overall_score,
            overall_level=overall_level.value,
            duration_ms=duration_ms,
        )
        return response

    # ------------------------------------------------------------------
    # Fan-out to external APIs
    # ------------------------------------------------------------------

    async def _fan_out(
        self, request: TrademarkSearchRequest
    ) -> tuple[dict[JurisdictionCode, TrademarkSearchResult], float | None]:
        """Run all searches in parallel; return per-jurisdiction results + common-law density."""
        tasks: list[asyncio.Task] = []
        task_labels: list[str] = []

        # Jurisdiction searches
        for jurisdiction in request.jurisdictions:
            api = self._apis.get(jurisdiction)
            if api is None:
                logger.warning("no_api_for_jurisdiction", jurisdiction=jurisdiction.value)
                continue
            tasks.append(
                asyncio.create_task(
                    self._bounded_search(api, request.phrase, request.nice_classes)
                )
            )
            task_labels.append(f"tm:{jurisdiction.value}")

        # Common-law check (optional)
        run_common_law = (
            request.check_common_law
            and self._common_law is not None
        )
        if run_common_law:
            tasks.append(asyncio.create_task(self._bounded_common_law(request.phrase)))
            task_labels.append("common_law")

        # Gather; never raise — all errors become per-task results
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)

        jurisdiction_results: dict[JurisdictionCode, TrademarkSearchResult] = {}
        common_law_density: float | None = None

        # Unpack results in order
        outcome_idx = 0
        for jurisdiction in request.jurisdictions:
            if jurisdiction not in self._apis:
                continue
            outcome = outcomes[outcome_idx]
            if isinstance(outcome, BaseException):
                # Should be rare — _bounded_search catches most errors internally
                logger.error(
                    "jurisdiction_search_crashed",
                    jurisdiction=jurisdiction.value,
                    error=str(outcome),
                )
                jurisdiction_results[jurisdiction] = TrademarkSearchResult(
                    jurisdiction=jurisdiction,
                    records=[],
                    duration_ms=0,
                    error=f"internal_error: {outcome}",
                )
            else:
                jurisdiction_results[jurisdiction] = outcome  # type: ignore[assignment]
            outcome_idx += 1

        if run_common_law:
            outcome = outcomes[outcome_idx]
            if isinstance(outcome, BaseException):
                logger.warning("common_law_crashed", error=str(outcome))
                common_law_density = 0.0
            else:
                common_law_density = float(outcome)  # type: ignore[arg-type]

        return jurisdiction_results, common_law_density

    async def _bounded_search(
        self,
        api: TrademarkAPI,
        phrase: str,
        nice_classes: list[int],
    ) -> TrademarkSearchResult:
        """Run a jurisdiction search with a timeout."""
        try:
            return await asyncio.wait_for(
                api.search(phrase=phrase, nice_classes=nice_classes),
                timeout=self._config.per_jurisdiction_timeout_seconds,
            )
        except asyncio.TimeoutError:
            return TrademarkSearchResult(
                jurisdiction=api.jurisdiction,
                records=[],
                duration_ms=int(self._config.per_jurisdiction_timeout_seconds * 1000),
                error="timeout",
            )
        except Exception as e:  # noqa: BLE001 — port contract says no raise, but safeguard
            logger.exception("jurisdiction_port_raised", jurisdiction=api.jurisdiction.value)
            return TrademarkSearchResult(
                jurisdiction=api.jurisdiction,
                records=[],
                duration_ms=0,
                error=f"unexpected: {e.__class__.__name__}",
            )

    async def _bounded_common_law(self, phrase: str) -> float:
        """Run common-law check with a timeout; degrade gracefully."""
        assert self._common_law is not None
        try:
            return await asyncio.wait_for(
                self._common_law.estimate_density(phrase),
                timeout=self._config.common_law_timeout_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning("common_law_timeout")
            return 0.0
        except Exception:  # noqa: BLE001
            logger.exception("common_law_raised")
            return 0.0

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_all(
        self,
        *,
        request: TrademarkSearchRequest,
        results: dict[JurisdictionCode, TrademarkSearchResult],
        common_law_density: float | None,
        genericness: float,
    ) -> list[JurisdictionRisk]:
        """Score every jurisdiction the user requested."""
        jurisdiction_risks: list[JurisdictionRisk] = []
        for jurisdiction in request.jurisdictions:
            result = results.get(jurisdiction)
            if result is None:
                # No API for this jurisdiction — report as unchecked
                jurisdiction_risks.append(
                    JurisdictionRisk(
                        code=jurisdiction,
                        risk_score=0,
                        risk_level=score_to_risk_level(0),
                        active_registrations=0,
                        pending_applications=0,
                        adjacent_class_registrations=0,
                        common_law_density=common_law_density,
                        arbitrage_available=False,
                        matching_records=[],
                        search_duration_ms=None,
                        error="no_api_configured",
                    )
                )
                continue

            jurisdiction_risks.append(
                self._scorer.score_jurisdiction(
                    jurisdiction=jurisdiction,
                    records=result.records,
                    target_nice_classes=request.nice_classes,
                    common_law_density=common_law_density,
                    phrase_genericness=genericness,
                    search_duration_ms=result.duration_ms,
                    search_error=result.error,
                )
            )
        return jurisdiction_risks

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    @staticmethod
    def _build_cache_key(request: TrademarkSearchRequest) -> str:
        """
        Deterministic cache key.

        Normalizes the phrase (lowercase, trimmed, single spaces) and sorts
        jurisdictions and classes so equivalent requests hit the same key.
        """
        normalized_phrase = " ".join(request.phrase.lower().split())
        payload = {
            "p": normalized_phrase,
            "j": sorted(j.value for j in request.jurisdictions),
            "n": sorted(request.nice_classes),
            "c": request.check_common_law,
        }
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        digest = hashlib.sha256(body.encode()).hexdigest()[:24]
        return f"{CACHE_KEY_PREFIX}:{digest}"

    async def _try_cache_get(self, key: str) -> TrademarkSearchResponse | None:
        """Read from cache; return None on any failure (caching is best-effort)."""
        assert self._cache is not None
        try:
            raw = await self._cache.get(key)
            if raw is None:
                return None
            data = orjson.loads(raw)
            response = TrademarkSearchResponse.model_validate(data)
            # Flip the flag — caller asked for fresh; we're serving cached
            return response.model_copy(update={"from_cache": True})
        except Exception:  # noqa: BLE001 — cache errors are non-fatal
            logger.warning("cache_get_failed", key=key)
            return None

    async def _try_cache_set(self, key: str, response: TrademarkSearchResponse) -> None:
        """Write to cache; swallow failures."""
        assert self._cache is not None
        try:
            payload = orjson.dumps(response.model_dump(mode="json"))
            await self._cache.set(key, payload, ttl_seconds=CACHE_TTL_SECONDS)
        except Exception:  # noqa: BLE001
            logger.warning("cache_set_failed", key=key)
