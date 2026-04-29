"""IP Australia adapter tests with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode
from scalemyprints.infrastructure.trademark_apis.ipau import (
    IPAU_DEFAULT_BASE_URL,
    IPAU_SEARCH_PATH,
    IPAustraliaClient,
)


def _sample_response(items: list[dict]) -> dict:
    return {"results": items, "total": len(items)}


def _sample_item(
    *,
    number: str = "2345678",
    words: str = "DOG MOM",
    status: str = "Registered",
    classes: list[int] | None = None,
    owner: str = "Acme Apparel Pty Ltd",
) -> dict:
    return {
        "tmNumber": number,
        "tmWords": words,
        "status": status,
        "classes": classes or [25],
        "owner": owner,
        "lodgeDate": "2020-03-15",
    }


class TestIPAustraliaClient:
    @respx.mock
    async def test_parses_results(self) -> None:
        respx.get(f"{IPAU_DEFAULT_BASE_URL}{IPAU_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_response([
                    _sample_item(number="2345678", status="Registered"),
                    _sample_item(number="2345679", status="Pending"),
                ]),
            )
        )
        async with IPAustraliaClient() as client:
            result = await client.search("dog mom", nice_classes=[25])

        assert result.jurisdiction == JurisdictionCode.AU
        assert result.error is None
        assert len(result.records) == 2
        assert {r.status for r in result.records} == {
            FilingStatus.REGISTERED,
            FilingStatus.PENDING,
        }

    @respx.mock
    async def test_filters_out_wrong_classes(self) -> None:
        # Server returns hits including class 30, but we asked for 25
        respx.get(f"{IPAU_DEFAULT_BASE_URL}{IPAU_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_response([
                    _sample_item(number="A1", classes=[25]),
                    _sample_item(number="A2", classes=[30]),
                ]),
            )
        )
        async with IPAustraliaClient() as client:
            result = await client.search("dog mom", nice_classes=[25])

        numbers = {r.registration_number for r in result.records}
        assert "A1" in numbers
        assert "A2" not in numbers

    @respx.mock
    async def test_empty_returns_empty(self) -> None:
        respx.get(f"{IPAU_DEFAULT_BASE_URL}{IPAU_SEARCH_PATH}").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        async with IPAustraliaClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is None
        assert result.records == []

    @respx.mock
    async def test_http_error_returns_error_result(self) -> None:
        respx.get(f"{IPAU_DEFAULT_BASE_URL}{IPAU_SEARCH_PATH}").mock(
            return_value=httpx.Response(503)
        )
        async with IPAustraliaClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is not None

    @respx.mock
    async def test_never_raises(self) -> None:
        respx.get(f"{IPAU_DEFAULT_BASE_URL}{IPAU_SEARCH_PATH}").mock(
            side_effect=httpx.ConnectError("network down")
        )
        async with IPAustraliaClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is not None
        assert result.records == []
