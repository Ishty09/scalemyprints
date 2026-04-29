"""Tests for pure normalizers."""

from __future__ import annotations

import pytest

from scalemyprints.domain.trademark.enums import FilingStatus
from scalemyprints.infrastructure.trademark_apis.normalizers import (
    normalize_date_string,
    normalize_filing_status,
    parse_nice_classes,
)


class TestNormalizeFilingStatus:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            # Registered variants
            ("REGISTERED", FilingStatus.REGISTERED),
            ("Registered", FilingStatus.REGISTERED),
            ("Live", FilingStatus.REGISTERED),
            ("live/registered", FilingStatus.REGISTERED),
            ("LIVE - REGISTERED", FilingStatus.REGISTERED),
            ("Protected", FilingStatus.REGISTERED),
            # Opposed
            ("Opposition Pending", FilingStatus.OPPOSED),
            ("Published for Opposition", FilingStatus.OPPOSED),
            # Pending
            ("Pending", FilingStatus.PENDING),
            ("Under Examination", FilingStatus.PENDING),
            ("New Application - Awaiting Examination", FilingStatus.PENDING),
            ("Filed", FilingStatus.PENDING),
            # Abandoned
            ("ABANDONED", FilingStatus.ABANDONED),
            ("Withdrawn", FilingStatus.ABANDONED),
            ("Lapsed", FilingStatus.ABANDONED),
            # Cancelled
            ("Cancelled", FilingStatus.CANCELLED),
            ("Canceled", FilingStatus.CANCELLED),
            ("Revoked", FilingStatus.CANCELLED),
            # Expired
            ("Expired", FilingStatus.EXPIRED),
            ("Not Renewed", FilingStatus.EXPIRED),
            ("DEAD", FilingStatus.EXPIRED),
        ],
    )
    def test_known_statuses(self, raw: str, expected: FilingStatus) -> None:
        assert normalize_filing_status(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [None, "", "   ", "something unknown gibberish"],
    )
    def test_unknown_returns_unknown(self, raw: str | None) -> None:
        assert normalize_filing_status(raw) == FilingStatus.UNKNOWN


class TestNormalizeDateString:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2024-01-15", "2024-01-15"),
            ("20240115", "2024-01-15"),
            ("2024-01-15T12:00:00", "2024-01-15"),
            ("2024-01-15T12:00:00Z", "2024-01-15"),
            ("2024-01-15T12:00:00.123Z", "2024-01-15"),
            ("15/01/2024", "2024-01-15"),
            ("15-01-2024", "2024-01-15"),
            ("15 Jan 2024", "2024-01-15"),
            ("15 January 2024", "2024-01-15"),
            ("2024-01-15T12:00:00+00:00", "2024-01-15"),
        ],
    )
    def test_parses_formats(self, raw: str, expected: str) -> None:
        assert normalize_date_string(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "   ", "not a date", "2024-13-45"])
    def test_unparseable_returns_none(self, raw: str | None) -> None:
        assert normalize_date_string(raw) is None


class TestParseNiceClasses:
    def test_none_returns_empty(self) -> None:
        assert parse_nice_classes(None) == []

    def test_integer_wrapped(self) -> None:
        assert parse_nice_classes(25) == [25]

    def test_out_of_range_integer_dropped(self) -> None:
        assert parse_nice_classes(99) == []
        assert parse_nice_classes(0) == []

    def test_list_of_ints(self) -> None:
        assert parse_nice_classes([25, 21, 16]) == [25, 21, 16]

    def test_list_dedupes(self) -> None:
        assert parse_nice_classes([25, 25, 21]) == [25, 21]

    def test_list_drops_invalid(self) -> None:
        assert parse_nice_classes([25, "bad", 99, 21]) == [25, 21]

    def test_string_comma_separated(self) -> None:
        assert parse_nice_classes("25, 21, 16") == [25, 21, 16]

    def test_string_with_prefix(self) -> None:
        assert parse_nice_classes("Class 25; Class 21") == [25, 21]

    def test_string_dedupes(self) -> None:
        assert parse_nice_classes("25, 25, 21") == [25, 21]

    def test_string_drops_out_of_range(self) -> None:
        assert parse_nice_classes("25, 99, 21") == [25, 21]

    def test_empty_string(self) -> None:
        assert parse_nice_classes("") == []
