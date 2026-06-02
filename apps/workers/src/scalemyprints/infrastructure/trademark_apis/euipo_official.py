"""
EUIPO Official Trademark Search adapter.

Uses EUIPO's OAuth2 Client Credentials flow (server-to-server) to query the
official EUIPO trademark search API. This is the **authoritative source** for
EU Trade Marks (EUTMs).

Implements TrademarkAPI protocol — drop-in compatible with the chain runner.

Auth flow:
  1. POST <token_url> with client_id+secret (Basic auth) and scope=uid
  2. Receive Bearer token (TTL ~3600s)
  3. Call GET <base_url>/trademarks with:
       - Authorization: Bearer <token>
       - X-IBM-Client-Id: <client_id>
  4. Cache token until ~60s before expiry; refresh on 401

API quirks (verified empirically):
  - Min page size = 10 (not 1)
  - RSQL query language for filters
  - Wildcards work on **single tokens only** — multi-word phrases quoted
    become exact-match. We split the phrase and AND each significant token.
  - niceClasses filter syntax: `niceClasses=all=(25)`
"""

from __future__ import annotations

import asyncio
import time
from types import TracebackType
from typing import Any

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.trademark.enums import (
    ACTIVE_STATUSES,
    FilingStatus,
    JurisdictionCode,
)
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
)

logger = get_logger(__name__)


PAGE_SIZE = 25  # EUIPO requires >= 10
TOKEN_REFRESH_LEEWAY_SECONDS = 60.0  # Refresh 60s before expiry
EUTM_DETAIL_URL_TEMPLATE = (
    "https://www.tmdn.org/tmview/welcome#/tmview/detail/EM50/{app_no}"
)


class EUIPOOfficialClient:
    """EUIPO OAuth2 trademark search client. Implements TrademarkAPI."""

    jurisdiction: JurisdictionCode = JurisdictionCode.EU

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        token_url: str,
        api_base_url: str,
        scope: str = "uid",
        http_factory: HttpClientFactory | None = None,
        client: httpx.AsyncClient | None = None,
        token_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not client_id or not client_secret:
            raise ValueError("EUIPO client_id and client_secret are required")

        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._scope = scope
        self._api_base_url = api_base_url.rstrip("/")

        factory = http_factory or HttpClientFactory()

        if client is not None:
            self._api_client = client
            self._owns_api_client = False
        else:
            self._api_client = factory.build(base_url=self._api_base_url)
            self._owns_api_client = True

        if token_client is not None:
            self._token_client = token_client
            self._owns_token_client = False
        else:
            # Separate client for the token endpoint (different base URL).
            self._token_client = factory.build(base_url="")
            self._owns_token_client = True

        # Token cache
        self._access_token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def __aenter__(self) -> EUIPOOfficialClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_api_client:
            await self._api_client.aclose()
        if self._owns_token_client:
            await self._token_client.aclose()

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    async def _get_token(self, *, force_refresh: bool = False) -> str:
        """Return a valid access token, refreshing if expired."""
        async with self._token_lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._access_token
                and now < self._token_expires_at - TOKEN_REFRESH_LEEWAY_SECONDS
            ):
                return self._access_token

            logger.info("euipo_token_refresh", scope=self._scope)
            try:
                response = await self._token_client.post(
                    self._token_url,
                    data={
                        "grant_type": "client_credentials",
                        "scope": self._scope,
                    },
                    auth=(self._client_id, self._client_secret),
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error(
                    "euipo_token_failed",
                    status=e.response.status_code,
                    body=e.response.text[:300],
                )
                raise
            except httpx.HTTPError as e:
                logger.error("euipo_token_network_error", error=str(e))
                raise

            payload = response.json()
            access_token = payload.get("access_token")
            expires_in = float(payload.get("expires_in", 3600))
            if not access_token:
                raise RuntimeError("EUIPO token response missing access_token")

            self._access_token = access_token
            self._token_expires_at = now + expires_in
            return access_token

    # ------------------------------------------------------------------
    # TrademarkAPI: search
    # ------------------------------------------------------------------

    async def search(
        self, phrase: str, nice_classes: list[int]
    ) -> TrademarkSearchResult:
        log = logger.bind(
            service="euipo_official",
            phrase=phrase,
            nice_classes=nice_classes,
        )

        async with measure_duration() as elapsed:
            try:
                results_per_class = await asyncio.gather(
                    *(self._search_one_class(phrase, nc) for nc in nice_classes),
                    return_exceptions=True,
                )

                combined: list[TrademarkRecord] = []
                error_messages: list[str] = []
                for nc, result in zip(nice_classes, results_per_class, strict=True):
                    if isinstance(result, BaseException):
                        error_messages.append(
                            f"class_{nc}:{result.__class__.__name__}"
                        )
                        log.warning(
                            "euipo_class_search_failed",
                            nice_class=nc,
                            error=str(result),
                        )
                    else:
                        combined.extend(result)

                deduped = _dedupe_records(combined)

                if error_messages and not combined:
                    return TrademarkSearchResult(
                        jurisdiction=self.jurisdiction,
                        records=[],
                        duration_ms=elapsed(),
                        error=f"all_failed: {'; '.join(error_messages)}",
                    )

                log.info(
                    "euipo_search_complete",
                    count=len(deduped),
                    duration_ms=elapsed(),
                )
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=deduped,
                    duration_ms=elapsed(),
                    error=None,
                )
            except Exception as e:
                log.exception("euipo_search_unexpected_error")
                return TrademarkSearchResult(
                    jurisdiction=self.jurisdiction,
                    records=[],
                    duration_ms=elapsed(),
                    error=f"unexpected:{e.__class__.__name__}",
                )

    # ------------------------------------------------------------------
    # Per-class search
    # ------------------------------------------------------------------

    async def _search_one_class(
        self, phrase: str, nice_class: int
    ) -> list[TrademarkRecord]:
        """Hit /trademarks with RSQL filter for one class."""
        rsql = _build_rsql_query(phrase, nice_class)
        params = {
            "query": rsql,
            "size": str(PAGE_SIZE),
        }

        async def _do_request_with_token() -> httpx.Response:
            token = await self._get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "X-IBM-Client-Id": self._client_id,
                "Accept": "application/json",
            }
            response = await self._api_client.get(
                "/trademarks", params=params, headers=headers
            )
            # On 401, force a token refresh and try once more.
            if response.status_code == 401:
                logger.info("euipo_token_401_refresh")
                token = await self._get_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                response = await self._api_client.get(
                    "/trademarks", params=params, headers=headers
                )
            response.raise_for_status()
            return response

        response = await run_with_retry(
            _do_request_with_token, service_name="euipo_official", max_attempts=3
        )

        try:
            payload = response.json()
        except ValueError:
            logger.warning("euipo_non_json_response", status=response.status_code)
            return []

        items = payload.get("trademarks") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            return []

        records: list[TrademarkRecord] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            parsed = self._parse_item(item, nice_class)
            if parsed is not None:
                records.append(parsed)
        return records

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_item(
        self, item: dict[str, Any], fallback_class: int
    ) -> TrademarkRecord | None:
        """Convert EUIPO `/trademarks` item → TrademarkRecord."""
        app_no = item.get("applicationNumber")
        if not app_no:
            return None
        app_no = str(app_no).strip()
        if not app_no:
            return None

        word_spec = item.get("wordMarkSpecification") or {}
        verbal = (
            word_spec.get("verbalElement") if isinstance(word_spec, dict) else None
        )
        mark = (verbal or "").strip() or "(no mark)"

        owner = _extract_owner(item)

        raw_status = item.get("status")
        status = normalize_filing_status(raw_status)

        nice_classes = _coerce_int_list(item.get("niceClasses")) or [fallback_class]

        filing_date = normalize_date_string(item.get("applicationDate"))
        registration_date = normalize_date_string(item.get("registrationDate"))

        is_active = status in ACTIVE_STATUSES
        is_pending = status == FilingStatus.PENDING

        return TrademarkRecord(
            registration_number=app_no,
            mark=mark,
            owner=owner,
            status=status,
            raw_status=str(raw_status) if raw_status is not None else None,
            nice_class=nice_classes[0] if nice_classes else None,
            nice_classes=nice_classes,
            filing_date=filing_date,
            registration_date=registration_date,
            jurisdiction=self.jurisdiction,
            source_url=EUTM_DETAIL_URL_TEMPLATE.format(app_no=app_no),
            goods_services=None,  # Not requested in `fields`; can opt in later
            is_active=is_active,
            is_pending=is_pending,
        )


# -----------------------------------------------------------------------------
# Pure helpers
# -----------------------------------------------------------------------------


# Tokens shorter than this are dropped from RSQL filters — too noisy/non-distinctive.
_MIN_TOKEN_LEN = 3
# Common English stop-words excluded from RSQL filters.
_STOP_WORDS: frozenset[str] = frozenset(
    {"THE", "AND", "FOR", "WITH", "OUR", "YOUR", "FROM"}
)
# Characters stripped from a phrase before tokenizing — RSQL reserves these.
_RSQL_RESERVED_CHARS = "(){}[],\"'!=<>;~"


def _build_rsql_query(phrase: str, nice_class: int) -> str:
    """
    Compose an RSQL query for EUIPO `/trademarks` from a free-text phrase.

    EUIPO's RSQL implementation only matches wildcards against single tokens.
    For a multi-word phrase we AND together one wildcard predicate per token.
    Stop-words and very short tokens are dropped to avoid noise. If no
    distinctive tokens remain (e.g., the user typed only stop-words), we
    fall back to the raw phrase as a single token to avoid an unbounded query.
    """
    cleaned = phrase
    for ch in _RSQL_RESERVED_CHARS:
        cleaned = cleaned.replace(ch, " ")
    tokens_raw = [t for t in cleaned.upper().split() if t]
    tokens = [
        t for t in tokens_raw if len(t) >= _MIN_TOKEN_LEN and t not in _STOP_WORDS
    ]
    if not tokens:
        tokens = [tokens_raw[0]] if tokens_raw else ["*"]

    predicates = [
        f"wordMarkSpecification.verbalElement==*{tok}*" for tok in tokens
    ]
    predicates.append(f"niceClasses=all=({nice_class})")
    return " and ".join(predicates)


def _extract_owner(item: dict[str, Any]) -> str | None:
    applicants = item.get("applicants")
    if not isinstance(applicants, list) or not applicants:
        return None
    first = applicants[0]
    if isinstance(first, dict):
        name = first.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return None


def _coerce_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    out: list[int] = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _dedupe_records(records: list[TrademarkRecord]) -> list[TrademarkRecord]:
    """Dedupe by application number; merge nice_classes lists when duplicated."""
    by_app: dict[str, TrademarkRecord] = {}
    for record in records:
        existing = by_app.get(record.registration_number)
        if existing is None:
            by_app[record.registration_number] = record
            continue
        merged_classes = list(existing.nice_classes)
        for nc in record.nice_classes:
            if nc not in merged_classes:
                merged_classes.append(nc)
        by_app[record.registration_number] = existing.model_copy(
            update={"nice_classes": merged_classes}
        )
    return list(by_app.values())
