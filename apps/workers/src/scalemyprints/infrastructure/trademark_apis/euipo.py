"""
EUIPO (European Union Intellectual Property Office) trademark adapter.

Implements TrademarkAPI. Uses EUIPO's eSearch JSON endpoint.

Note: EUIPO's public API shape has changed over the years. We query the
documented endpoint and degrade gracefully on schema drift.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Any

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.enums import ACTIVE_STATUSES, FilingStatus, JurisdictionCode
from scalemyprints.domain.trademark.models import TrademarkRecord
from scalemyprints.domain.trademark.ports import TrademarkSearchResult
from scalemyprints.infrastructure.trademark_apis.base import (
    HttpClientFactory,
    measure_duration,
    run_with_retry,
)
from scalemyprints.infrastructure.trademark_apis.normalizers import (
    normalize_date_string,
    normalize_filing_status,
    parse_nice_classes,
)

logger = get_logger(__name__)


EUIPO_DEFAULT_BASE_URL = "https://euipo.europa.eu/copla"
EUIPO_SEARCH_PATH = "/trademark/data/search"
MAX_RESULTS = 50

EUIPO_DETAIL_URL_TEMPLATE = (
    "https://euipo.europa.eu/eSearch/#details/trademarks/{number}"
)


class EUIPOClient:
    """EUIPO trademark search client."""

    jurisdiction: JurisdictionCode = JurisdictionCode.EU

    def __init__(
        self,
        *,
        base_url: str = EUIPO_DEFAULT_BASE_URL,
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            factory = http_factory or HttpClientFactory()
            self._client = factory.build(base_url=self._base_url)
            self._owns_client = True

    async def __aenter__(self) -> "EUIPOClient":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        log = logger.bind(service="euipo", phrase=phrase, nice_classes=nice_classes)
        async with measure_duration() as elapsed:
            try:
                results_per_class = await asyncio.gather(
                    *(self._search_one_class(phrase, nc) for nc in nice_classes),
                    return_exceptions=True,
                )

                combined: list[TrademarkRecord] = []
                errors: list[str] = []
                for nc, res in zip(nice_classes, results_per_class, strict=True):
                    if isinstance(res, BaseException):
                        errors.append(f"class_{nc}:{res.__class__.__name__}")
                        log.warning("euipo_class_failed", nice_class=nc, error=str(res))
                    else:
                        combined.extend(res)

                deduped = _dedupe_records(combined)

                if errors and not combined:
                    return TrademarkSearchResult(
                        jurisdiction=self.jurisdiction,
                        records=[],
                        duration_ms=elapsed(),
                        error=f"all_failed: {'; '.join(errors)}",
                    )

                log.info("euipo_search_complete", count=len(deduped), duration_ms=elapsed())
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=deduped,
                    duration_ms=elapsed(),
                    error=None,
                )
            except Exception as e:  # noqa: BLE001
                log.exception("euipo_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    async def _search_one_class(
        self, phrase: str, nice_class: int
    ) -> list[TrademarkRecord]:
        params = {
            "text": phrase,
            "niceClass": str(nice_class),
            "limit": str(MAX_RESULTS),
            "status": "all",
        }

        async def _do() -> httpx.Response:
            response = await self._client.get(EUIPO_SEARCH_PATH, params=params)
            if response.status_code == 404:
                return response
            response.raise_for_status()
            return response

        response = await run_with_retry(_do, service_name="euipo", max_attempts=3)
        if response.status_code == 404:
            return []

        try:
            payload = response.json()
        except ValueError:
            return []

        raw_items = _extract_items(payload)
        records = [self._parse_item(item, nice_class) for item in raw_items]
        return [r for r in records if r is not None]

    def _parse_item(self, item: dict[str, Any], fallback_class: int) -> TrademarkRecord | None:
        number = (
            item.get("tradeMarkNumber")
            or item.get("number")
            or item.get("applicationNumber")
        )
        if not number:
            return None

        mark = (
            item.get("tradeMarkName")
            or item.get("mark")
            or item.get("verbalElements")
            or ""
        )
        raw_status = (
            item.get("status")
            or item.get("tradeMarkStatus")
            or item.get("markStatus")
        )
        status = normalize_filing_status(raw_status)

        nice_classes = parse_nice_classes(
            item.get("niceClasses")
            or item.get("classes")
            or item.get("classifications")
        )
        if not nice_classes:
            nice_classes = [fallback_class]

        owner = _extract_owner(item)
        filing_date = normalize_date_string(item.get("filingDate") or item.get("applicationDate"))
        registration_date = normalize_date_string(
            item.get("registrationDate") or item.get("dateOfRegistration")
        )

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        return TrademarkRecord(
            registration_number=str(number),
            mark=str(mark).strip() or "(no mark)",
            owner=owner,
            status=status,
            raw_status=str(raw_status) if raw_status else None,
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=EUIPO_DETAIL_URL_TEMPLATE.format(number=number),
            goods_services=item.get("goodsAndServices") or item.get("goods"),
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Module helpers
# -----------------------------------------------------------------------------


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [i for i in payload if isinstance(i, dict)]
    if isinstance(payload, dict):
        for key in ("results", "data", "items", "hits", "tradeMarks"):
            value = payload.get(key)
            if isinstance(value, list):
                return [i for i in value if isinstance(i, dict)]
    return []


def _extract_owner(item: dict[str, Any]) -> str | None:
    for key in ("owner", "ownerName", "applicant", "applicantName"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            name = value.get("name") or value.get("displayName")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return None


def _dedupe_records(records: list[TrademarkRecord]) -> list[TrademarkRecord]:
    by_number: dict[str, TrademarkRecord] = {}
    for record in records:
        existing = by_number.get(record.registration_number)
        if existing is None:
            by_number[record.registration_number] = record
            continue
        merged_classes = list(existing.nice_classes)
        for nc in record.nice_classes:
            if nc not in merged_classes:
                merged_classes.append(nc)
        by_number[record.registration_number] = existing.model_copy(
            update={"nice_classes": merged_classes}
        )
    return list(by_number.values())
