"""
Source-specific → domain normalizers.

Pure functions that translate the quirky status strings and date formats
each trademark office returns into our normalized domain enums.

Tested independently so we catch regressions without hitting real APIs.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from scalemyprints.domain.trademark.enums import FilingStatus

# -----------------------------------------------------------------------------
# Filing status normalization
# -----------------------------------------------------------------------------

# Keyword → normalized status. Order matters: check most specific first.
# All keys are lowercase; input is lowercased before matching.
_STATUS_KEYWORDS: list[tuple[str, FilingStatus]] = [
    # Registered / live / protected
    ("registered", FilingStatus.REGISTERED),
    ("registration", FilingStatus.REGISTERED),
    ("live", FilingStatus.REGISTERED),
    ("protected", FilingStatus.REGISTERED),
    # Opposition / published for opposition
    ("opposition", FilingStatus.OPPOSED),
    ("opposed", FilingStatus.OPPOSED),
    ("published for opposition", FilingStatus.OPPOSED),
    # Pending / under examination
    ("pending", FilingStatus.PENDING),
    ("examination", FilingStatus.PENDING),
    ("examined", FilingStatus.PENDING),
    ("filed", FilingStatus.PENDING),
    ("new application", FilingStatus.PENDING),
    ("awaiting", FilingStatus.PENDING),
    # Abandoned (applicant dropped)
    ("abandoned", FilingStatus.ABANDONED),
    ("withdrawn", FilingStatus.ABANDONED),
    ("lapsed", FilingStatus.ABANDONED),
    # Cancelled (office-cancelled)
    ("cancelled", FilingStatus.CANCELLED),
    ("canceled", FilingStatus.CANCELLED),
    ("revoked", FilingStatus.CANCELLED),
    ("invalidated", FilingStatus.CANCELLED),
    # Expired
    ("expired", FilingStatus.EXPIRED),
    ("not renewed", FilingStatus.EXPIRED),
    ("dead", FilingStatus.EXPIRED),
]


def normalize_filing_status(raw_status: str | None) -> FilingStatus:
    """
    Translate a source office's status string to our domain enum.

    Unknown statuses return FilingStatus.UNKNOWN — we never guess.
    Empty/None returns UNKNOWN.
    """
    if not raw_status:
        return FilingStatus.UNKNOWN

    normalized = raw_status.strip().lower()
    if not normalized:
        return FilingStatus.UNKNOWN

    for keyword, status in _STATUS_KEYWORDS:
        if keyword in normalized:
            return status
    return FilingStatus.UNKNOWN


# -----------------------------------------------------------------------------
# Date normalization
# -----------------------------------------------------------------------------

# Accepted input formats, in order of preference
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%fZ",
    "%Y%m%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%d %b %Y",
    "%d %B %Y",
]

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def normalize_date_string(raw: str | None) -> str | None:
    """
    Normalize a date string to ISO-8601 (YYYY-MM-DD).

    Returns None for empty/unparseable inputs.
    """
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None

    # Fast path: already ISO-shaped — but still parse to validate ranges
    if _ISO_DATE_RE.match(stripped):
        try:
            parsed = datetime.strptime(stripped, "%Y-%m-%d")  # noqa: DTZ007
            return parsed.date().isoformat()
        except ValueError:
            return None

    # Try formats in order
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(stripped, fmt)  # noqa: DTZ007 — trademark filings are just dates
            return dt.date().isoformat()
        except ValueError:
            continue

    # Try fromisoformat (Python 3.11+ handles many shapes)
    try:
        dt = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        pass

    return None


def today_iso() -> str:
    """Today's date as ISO string — testable replacement for hardcoded dates."""
    return date.today().isoformat()  # noqa: DTZ011 — date-only is timezone-neutral


# -----------------------------------------------------------------------------
# Nice class parsing
# -----------------------------------------------------------------------------

_NICE_CLASS_RE = re.compile(r"\b(\d{1,2})\b")


def parse_nice_classes(raw: str | int | list | None) -> list[int]:
    """
    Parse Nice classes from various formats:
    - None → []
    - int (25) → [25]
    - list → validated ints
    - str ("25, 21") → [25, 21]
    - str ("Class 25; Class 21") → [25, 21]

    Invalid/out-of-range classes are silently dropped.
    """
    if raw is None:
        return []
    if isinstance(raw, int):
        return [raw] if 1 <= raw <= 45 else []
    if isinstance(raw, list):
        out: list[int] = []
        for item in raw:
            try:
                value = int(item)
                if 1 <= value <= 45:
                    out.append(value)
            except (ValueError, TypeError):
                continue
        return _dedupe_preserve_order(out)
    if isinstance(raw, str):
        matches = _NICE_CLASS_RE.findall(raw)
        values = [int(m) for m in matches if 1 <= int(m) <= 45]
        return _dedupe_preserve_order(values)
    return []


def _dedupe_preserve_order(values: list[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out
