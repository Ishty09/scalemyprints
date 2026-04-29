"""
Tests for TrademarkSearchService — the orchestrator.

Uses in-memory fakes for all ports (TrademarkAPI, CacheStore, CommonLawChecker)
so these run in milliseconds with no real network/DB.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from scalemyprints.domain.shared.clock import FixedClock
from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode, RiskLevel
from scalemyprints.domain.trademark.models import TrademarkSearchRequest
from scalemyprints.domain.trademark.ports import TrademarkAPI, TrademarkSearchResult
from scalemyprints.domain.trademark.search_service import (
    SearchServiceConfig,
    TrademarkSearchService,
)
from tests.fixtures import make_record


# -----------------------------------------------------------------------------
# In-memory fakes
# -----------------------------------------------------------------------------


@dataclass
class FakeTrademarkAPI:
    """In-memory TrademarkAPI for tests. Implements the TrademarkAPI protocol."""

    jurisdiction: JurisdictionCode
    records_to_return: list = field(default_factory=list)
    should_raise: Exception | None = None
    should_return_error: str | None = None
    delay_seconds: float = 0.0
    call_count: int = 0

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        self.call_count += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.should_raise:
            raise self.should_raise
        return TrademarkSearchResult(
            jurisdiction=self.jurisdiction,
            records=list(self.records_to_return),
            duration_ms=100,
            error=self.should_return_error,
        )


class FakeCache:
    """In-memory cache."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.get_calls = 0
        self.set_calls = 0

    async def get(self, key: str) -> bytes | None:
        self.get_calls += 1
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        self.set_calls += 1
        self.store[key] = value

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)


class FakeCommonLawChecker:
    def __init__(self, density: float = 0.0, should_raise: Exception | None = None) -> None:
        self.density = density
        self.should_raise = should_raise

    async def estimate_density(self, phrase: str) -> float:
        if self.should_raise:
            raise self.should_raise
        return self.density


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def build_service(
    *,
    apis: dict[JurisdictionCode, TrademarkAPI] | None = None,
    cache: FakeCache | None = None,
    common_law: FakeCommonLawChecker | None = None,
    clock: FixedClock | None = None,
    config: SearchServiceConfig | None = None,
) -> TrademarkSearchService:
    from datetime import UTC, datetime

    default_apis: dict[JurisdictionCode, TrademarkAPI] = apis or {
        JurisdictionCode.US: FakeTrademarkAPI(jurisdiction=JurisdictionCode.US),
        JurisdictionCode.EU: FakeTrademarkAPI(jurisdiction=JurisdictionCode.EU),
        JurisdictionCode.AU: FakeTrademarkAPI(jurisdiction=JurisdictionCode.AU),
    }
    return TrademarkSearchService(
        trademark_apis=default_apis,
        cache=cache,
        common_law_checker=common_law,
        clock=clock or FixedClock(datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)),
        config=config or SearchServiceConfig(cache_enabled=cache is not None),
    )


# -----------------------------------------------------------------------------
# Construction
# -----------------------------------------------------------------------------


class TestConstruction:
    def test_requires_at_least_one_api(self) -> None:
        with pytest.raises(ValueError, match="At least one TrademarkAPI"):
            TrademarkSearchService(trademark_apis={})


# -----------------------------------------------------------------------------
# Basic search flow
# -----------------------------------------------------------------------------


class TestSearchHappyPath:
    async def test_no_hits_returns_safe(self) -> None:
        service = build_service()
        request = TrademarkSearchRequest(
            phrase="Zylonka",
            jurisdictions=[JurisdictionCode.US],
            nice_classes=[25],
            check_common_law=False,
        )
        response = await service.search(request)

        assert response.phrase == "Zylonka"
        assert response.overall_risk_level == RiskLevel.SAFE
        assert len(response.jurisdictions) == 1
        assert response.jurisdictions[0].code == JurisdictionCode.US
        assert response.from_cache is False
        assert response.duration_ms >= 0

    async def test_us_hit_produces_appropriate_risk_level(self) -> None:
        us_api = FakeTrademarkAPI(
            jurisdiction=JurisdictionCode.US,
            records_to_return=[
                make_record(status=FilingStatus.REGISTERED, nice_class=25),
                make_record(
                    registration_number="98100002",
                    status=FilingStatus.REGISTERED,
                    nice_class=25,
                ),
                make_record(
                    registration_number="98100003",
                    status=FilingStatus.REGISTERED,
                    nice_class=25,
                ),
            ],
        )
        service = build_service(apis={JurisdictionCode.US: us_api})
        request = TrademarkSearchRequest(
            phrase="Brand",
            jurisdictions=[JurisdictionCode.US],
            nice_classes=[25],
            check_common_law=False,
        )
        response = await service.search(request)

        assert response.overall_risk_score > 0
        assert response.jurisdictions[0].active_registrations == 3

    async def test_parallel_fan_out_all_apis_called(self) -> None:
        us = FakeTrademarkAPI(jurisdiction=JurisdictionCode.US)
        eu = FakeTrademarkAPI(jurisdiction=JurisdictionCode.EU)
        au = FakeTrademarkAPI(jurisdiction=JurisdictionCode.AU)
        service = build_service(
            apis={
                JurisdictionCode.US: us,
                JurisdictionCode.EU: eu,
                JurisdictionCode.AU: au,
            }
        )
        await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[
                    JurisdictionCode.US,
                    JurisdictionCode.EU,
                    JurisdictionCode.AU,
                ],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        assert us.call_count == 1
        assert eu.call_count == 1
        assert au.call_count == 1


# -----------------------------------------------------------------------------
# Error handling / graceful degradation
# -----------------------------------------------------------------------------


class TestErrorHandling:
    async def test_one_jurisdiction_error_doesnt_break_others(self) -> None:
        us_ok = FakeTrademarkAPI(jurisdiction=JurisdictionCode.US)
        eu_err = FakeTrademarkAPI(
            jurisdiction=JurisdictionCode.EU, should_return_error="api_down"
        )
        service = build_service(
            apis={JurisdictionCode.US: us_ok, JurisdictionCode.EU: eu_err}
        )
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US, JurisdictionCode.EU],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        us_result = next(j for j in response.jurisdictions if j.code == JurisdictionCode.US)
        eu_result = next(j for j in response.jurisdictions if j.code == JurisdictionCode.EU)
        assert us_result.error is None
        assert eu_result.error == "api_down"

    async def test_port_that_raises_is_caught(self) -> None:
        us_crash = FakeTrademarkAPI(
            jurisdiction=JurisdictionCode.US,
            should_raise=RuntimeError("catastrophe"),
        )
        service = build_service(apis={JurisdictionCode.US: us_crash})
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        assert response.jurisdictions[0].error is not None
        assert "unexpected" in response.jurisdictions[0].error.lower()

    async def test_slow_jurisdiction_times_out(self) -> None:
        slow = FakeTrademarkAPI(
            jurisdiction=JurisdictionCode.US,
            delay_seconds=2.0,
        )
        service = build_service(
            apis={JurisdictionCode.US: slow},
            config=SearchServiceConfig(per_jurisdiction_timeout_seconds=0.1),
        )
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        assert response.jurisdictions[0].error == "timeout"

    async def test_common_law_failure_degrades_to_zero(self) -> None:
        service = build_service(
            common_law=FakeCommonLawChecker(should_raise=RuntimeError("boom"))
        )
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=True,
            )
        )
        # Service still returns a response; common-law signal just missing
        assert response.overall_risk_level in (RiskLevel.SAFE, RiskLevel.LOW)


# -----------------------------------------------------------------------------
# Cache behavior
# -----------------------------------------------------------------------------


class TestCaching:
    async def test_second_identical_call_hits_cache(self) -> None:
        cache = FakeCache()
        us_api = FakeTrademarkAPI(jurisdiction=JurisdictionCode.US)
        service = build_service(
            apis={JurisdictionCode.US: us_api},
            cache=cache,
        )
        request = TrademarkSearchRequest(
            phrase="test phrase",
            jurisdictions=[JurisdictionCode.US],
            nice_classes=[25],
            check_common_law=False,
        )

        r1 = await service.search(request)
        r2 = await service.search(request)

        assert r1.from_cache is False
        assert r2.from_cache is True
        assert us_api.call_count == 1  # API called only once
        assert cache.get_calls == 2
        assert cache.set_calls == 1

    async def test_different_phrase_different_cache_key(self) -> None:
        cache = FakeCache()
        us_api = FakeTrademarkAPI(jurisdiction=JurisdictionCode.US)
        service = build_service(
            apis={JurisdictionCode.US: us_api},
            cache=cache,
        )
        await service.search(
            TrademarkSearchRequest(
                phrase="phrase A",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        await service.search(
            TrademarkSearchRequest(
                phrase="phrase B",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        # Both should hit the API (different cache keys)
        assert us_api.call_count == 2

    async def test_cache_key_is_normalization_invariant(self) -> None:
        """Same phrase with different casing/whitespace hits same cache key."""
        cache = FakeCache()
        us_api = FakeTrademarkAPI(jurisdiction=JurisdictionCode.US)
        service = build_service(
            apis={JurisdictionCode.US: us_api},
            cache=cache,
        )
        req_a = TrademarkSearchRequest(
            phrase="test phrase",
            jurisdictions=[JurisdictionCode.US],
            nice_classes=[25],
            check_common_law=False,
        )
        req_b = TrademarkSearchRequest(
            phrase="TEST   PHRASE",  # Different case + extra spaces
            jurisdictions=[JurisdictionCode.US],
            nice_classes=[25],
            check_common_law=False,
        )
        await service.search(req_a)
        await service.search(req_b)
        # Second call should be cache hit — same normalized phrase
        assert us_api.call_count == 1


# -----------------------------------------------------------------------------
# Output invariants
# -----------------------------------------------------------------------------


class TestResponseInvariants:
    async def test_response_passes_pydantic_validation(self) -> None:
        service = build_service()
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US, JurisdictionCode.EU],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        # If we get here, the response passed Pydantic validation
        assert 0 <= response.overall_risk_score <= 100
        assert 0.0 <= response.phrase_genericness <= 1.0
        assert response.analyzed_at is not None

    async def test_response_includes_all_requested_jurisdictions(self) -> None:
        service = build_service()
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US, JurisdictionCode.EU, JurisdictionCode.AU],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        returned_codes = {j.code for j in response.jurisdictions}
        assert returned_codes == {
            JurisdictionCode.US,
            JurisdictionCode.EU,
            JurisdictionCode.AU,
        }

    async def test_analyzed_at_uses_injected_clock(self) -> None:
        from datetime import UTC, datetime

        fixed = FixedClock(datetime(2030, 6, 15, 10, 30, 0, tzinfo=UTC))
        service = build_service(clock=fixed)
        response = await service.search(
            TrademarkSearchRequest(
                phrase="test",
                jurisdictions=[JurisdictionCode.US],
                nice_classes=[25],
                check_common_law=False,
            )
        )
        assert response.analyzed_at == fixed.now()
