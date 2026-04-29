"""EUIPO adapter tests with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode
from scalemyprints.infrastructure.trademark_apis.euipo import (
    EUIPO_DEFAULT_BASE_URL,
    EUIPO_SEARCH_PATH,
    EUIPOClient,
)


def _sample_response(items: list[dict]) -> dict:
    return {"tradeMarks": items, "total": len(items)}


def _sample_item(
    *,
    number: str = "018123456",
    mark: str = "DOG MOM",
    status: str = "REGISTERED",
    nice_classes: list[int] | None = None,
    owner: str = "Acme Apparel LLC",
) -> dict:
    return {
        "tradeMarkNumber": number,
        "tradeMarkName": mark,
        "status": status,
        "niceClasses": nice_classes or [25],
        "owner": owner,
        "filingDate": "2020-03-15",
    }


class TestEUIPOClient:
    @respx.mock
    async def test_parses_results(self) -> None:
        respx.get(f"{EUIPO_DEFAULT_BASE_URL}{EUIPO_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_response([
                    _sample_item(number="018111111", status="REGISTERED"),
                    _sample_item(number="018222222", status="Opposition"),
                ]),
            )
        )
        async with EUIPOClient() as client:
            result = await client.search("dog mom", nice_classes=[25])

        assert result.jurisdiction == JurisdictionCode.EU
        assert result.error is None
        assert len(result.records) == 2
        assert {r.status for r in result.records} == {
            FilingStatus.REGISTERED,
            FilingStatus.OPPOSED,
        }
        # Source URL points to eSearch detail
        assert all(
            r.source_url is not None and "euipo.europa.eu" in r.source_url
            for r in result.records
        )

    @respx.mock
    async def test_empty_returns_empty(self) -> None:
        respx.get(f"{EUIPO_DEFAULT_BASE_URL}{EUIPO_SEARCH_PATH}").mock(
            return_value=httpx.Response(200, json={"tradeMarks": []})
        )
        async with EUIPOClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is None
        assert result.records == []

    @respx.mock
    async def test_network_error_returns_error_result(self) -> None:
        respx.get(f"{EUIPO_DEFAULT_BASE_URL}{EUIPO_SEARCH_PATH}").mock(
            side_effect=httpx.ConnectError("boom")
        )
        async with EUIPOClient() as client:
            result = await client.search("test", nice_classes=[25])
        assert result.error is not None

    @respx.mock
    async def test_nice_classes_parsed_from_list(self) -> None:
        respx.get(f"{EUIPO_DEFAULT_BASE_URL}{EUIPO_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_response([_sample_item(nice_classes=[25, 18])]),
            )
        )
        async with EUIPOClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert len(result.records) == 1
        assert sorted(result.records[0].nice_classes) == [18, 25]
