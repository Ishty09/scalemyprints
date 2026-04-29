"""
USPTO adapter tests.

Uses respx to mock httpx so we exercise real parsing and error handling
without hitting the internet.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from scalemyprints.domain.trademark.enums import FilingStatus, JurisdictionCode
from scalemyprints.infrastructure.trademark_apis.uspto import (
    USPTO_DEFAULT_BASE_URL,
    USPTO_SEARCH_PATH,
    USPTOClient,
    _dedupe_records,
    _extract_items,
)
from tests.fixtures import make_record

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sample_uspto_response(items: list[dict]) -> dict:
    """USPTO returns results under a `results` key."""
    return {"results": items, "total": len(items)}


def _sample_item(
    *,
    serial: str = "98100001",
    mark: str = "DOG MOM",
    status: str = "REGISTERED",
    nice_class: int = 25,
    owner: str = "Acme Apparel LLC",
) -> dict:
    return {
        "serialNumber": serial,
        "markIdentification": mark,
        "statusDescription": status,
        "niceClass": str(nice_class),
        "ownerName": owner,
        "filingDate": "2020-03-15",
        "registrationDate": "2021-09-20",
        "goodsAndServices": "Apparel, namely t-shirts",
    }


# ---------------------------------------------------------------------------
# Module-level helper tests
# ---------------------------------------------------------------------------


class TestExtractItems:
    def test_handles_list_payload(self) -> None:
        assert _extract_items([{"a": 1}, {"b": 2}]) == [{"a": 1}, {"b": 2}]

    def test_handles_results_wrapper(self) -> None:
        assert _extract_items({"results": [{"a": 1}]}) == [{"a": 1}]

    def test_handles_data_wrapper(self) -> None:
        assert _extract_items({"data": [{"a": 1}]}) == [{"a": 1}]

    def test_empty_payload_returns_empty(self) -> None:
        assert _extract_items({}) == []
        assert _extract_items([]) == []
        assert _extract_items(None) == []

    def test_filters_non_dict_items(self) -> None:
        assert _extract_items({"results": [{"ok": 1}, "junk", None]}) == [{"ok": 1}]


class TestDedupeRecords:
    def test_empty_input(self) -> None:
        assert _dedupe_records([]) == []

    def test_no_duplicates_passthrough(self) -> None:
        records = [
            make_record(registration_number="A", nice_class=25),
            make_record(registration_number="B", nice_class=25),
        ]
        assert _dedupe_records(records) == records

    def test_merges_nice_classes_for_duplicate_serial(self) -> None:
        records = [
            make_record(registration_number="SAME", nice_class=25),
            make_record(registration_number="SAME", nice_class=21),
        ]
        result = _dedupe_records(records)
        assert len(result) == 1
        assert sorted(result[0].nice_classes) == [21, 25]


# ---------------------------------------------------------------------------
# Client integration tests (respx-mocked)
# ---------------------------------------------------------------------------


class TestUSPTOClientSearch:
    @respx.mock
    async def test_returns_parsed_records_on_success(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_uspto_response([
                    _sample_item(serial="98100001", mark="DOG MOM", status="REGISTERED"),
                    _sample_item(serial="98100002", mark="DOG MOM", status="PENDING"),
                ]),
            )
        )
        async with USPTOClient() as client:
            result = await client.search("dog mom", nice_classes=[25])

        assert result.jurisdiction == JurisdictionCode.US
        assert result.error is None
        assert len(result.records) == 2
        assert {r.status for r in result.records} == {
            FilingStatus.REGISTERED,
            FilingStatus.PENDING,
        }
        first = next(r for r in result.records if r.registration_number == "98100001")
        assert first.is_active is True
        assert first.mark == "DOG MOM"
        assert first.owner == "Acme Apparel LLC"
        assert first.nice_class == 25
        assert first.source_url is not None
        assert "98100001" in first.source_url

    @respx.mock
    async def test_empty_results_returns_empty_records(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        async with USPTOClient() as client:
            result = await client.search("xyzqwerty", nice_classes=[25])

        assert result.error is None
        assert result.records == []

    @respx.mock
    async def test_404_treated_as_empty_results(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(404, json={"message": "not found"})
        )
        async with USPTOClient() as client:
            result = await client.search("nothing", nice_classes=[25])

        assert result.error is None
        assert result.records == []

    @respx.mock
    async def test_500_returns_error_result(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(500, json={"error": "boom"})
        )
        async with USPTOClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is not None
        assert result.records == []

    @respx.mock
    async def test_non_json_response_handled(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(200, text="<html>not json</html>")
        )
        async with USPTOClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.error is None
        assert result.records == []

    @respx.mock
    async def test_multiple_nice_classes_merged(self) -> None:
        """Same serial returned for two class queries → merged into one record."""
        # Return class 25 result when query asks for class 25
        respx.get(
            f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}",
            params={"niceClass": "25"},
        ).mock(
            return_value=httpx.Response(
                200,
                json=_sample_uspto_response([_sample_item(serial="98100001", nice_class=25)]),
            )
        )
        # Return class 21 result (same serial, different class) when asked for 21
        respx.get(
            f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}",
            params={"niceClass": "21"},
        ).mock(
            return_value=httpx.Response(
                200,
                json=_sample_uspto_response([_sample_item(serial="98100001", nice_class=21)]),
            )
        )
        async with USPTOClient() as client:
            result = await client.search("dog mom", nice_classes=[25, 21])

        # Deduped to one record; nice_classes merged from both responses
        assert len(result.records) == 1
        assert sorted(result.records[0].nice_classes) == [21, 25]

    @respx.mock
    async def test_never_raises_even_on_catastrophic_error(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            side_effect=httpx.ConnectError("network down")
        )
        async with USPTOClient() as client:
            # Port contract: must not raise
            result = await client.search("test", nice_classes=[25])

        assert result.error is not None
        assert result.records == []

    @respx.mock
    async def test_duration_ms_recorded(self) -> None:
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(200, json={"results": []})
        )
        async with USPTOClient() as client:
            result = await client.search("test", nice_classes=[25])

        assert result.duration_ms >= 0

    @respx.mock
    async def test_malformed_record_skipped(self) -> None:
        """Records missing required fields should be dropped, not crash parsing."""
        respx.get(f"{USPTO_DEFAULT_BASE_URL}{USPTO_SEARCH_PATH}").mock(
            return_value=httpx.Response(
                200,
                json=_sample_uspto_response([
                    _sample_item(serial="98100001"),
                    {"noSerial": "whoops"},  # malformed — missing serial
                    {},  # completely empty
                ]),
            )
        )
        async with USPTOClient() as client:
            result = await client.search("test", nice_classes=[25])

        # Only the valid record comes through
        assert len(result.records) == 1
        assert result.records[0].registration_number == "98100001"
