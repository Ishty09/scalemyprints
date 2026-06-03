"""
Supabase-backed implementations of WatchlistStore / AlertStore / ApiKeyStore.

REST/PostgREST style identical to the Phase 1 SupabaseListingStore.
Uses the service role key — bypasses RLS, since the worker process
is the writer.

Schemas:
- spy_watchlists       (Phase 4 migration)
- spy_alerts           (Phase 4 migration)
- spy_api_keys         (Phase 4 migration)
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import (
    Alert,
    AlertChannel,
    AlertChannelConfig,
    AlertStatus,
    AlertTrigger,
    SpyApiKey,
    Watchlist,
    WatchType,
)
from scalemyprints.domain.spy.watchlist_service import AlertStore, WatchlistStore

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class _PostgrestBase:
    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        timeout_seconds: float = 6.0,
    ) -> None:
        self._url = supabase_url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


# -----------------------------------------------------------------------------
# Watchlists
# -----------------------------------------------------------------------------


class SupabaseWatchlistStore(_PostgrestBase, WatchlistStore):
    """spy_watchlists CRUD over PostgREST."""

    async def create(self, watchlist: Watchlist) -> Watchlist:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        headers = {**self._headers, "Prefer": "return=representation"}
        payload = _serialize_watchlist(watchlist)
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "spy_watchlist_create_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )
            resp.raise_for_status()
        rows = resp.json()
        if not rows:
            return watchlist
        return _row_to_watchlist(rows[0])

    async def get(self, watchlist_id: str, user_id: str) -> Watchlist | None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {"id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}", "select": "*"}
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        return _row_to_watchlist(rows[0]) if rows else None

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_watchlist(r) for r in resp.json()]

    async def update(self, watchlist: Watchlist) -> Watchlist:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {"id": f"eq.{watchlist.id}"}
        headers = {**self._headers, "Prefer": "return=representation"}
        payload = _serialize_watchlist(watchlist)
        resp = await client.patch(url, params=params, headers=headers, json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        rows = resp.json()
        return _row_to_watchlist(rows[0]) if rows else watchlist

    async def delete(self, watchlist_id: str, user_id: str) -> bool:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {"id": f"eq.{watchlist_id}", "user_id": f"eq.{user_id}"}
        headers = {**self._headers, "Prefer": "return=representation"}
        resp = await client.delete(url, params=params, headers=headers)
        if resp.status_code >= 400:
            return False
        return bool(resp.json())

    async def matching_phrases(self, phrase: str) -> list[Watchlist]:
        norm = (phrase or "").strip().lower()
        if not norm:
            return []
        client = await self._http()
        # PostgREST `ilike` on target — '%target%' against the observed
        # phrase is reversed (we want target IN phrase). Easiest:
        # fetch all enabled phrase watchlists and filter in-process. For
        # 1k-scale users this is fine; later: materialized phrase index.
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {
            "watch_type": "in.(phrase,viral_category)",
            "enabled": "eq.true",
            "select": "*",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        rows = resp.json()
        return [
            _row_to_watchlist(r)
            for r in rows
            if str(r.get("target", "")).strip().lower() in norm
        ]

    async def matching_listings(self, listing_id: str) -> list[Watchlist]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {
            "watch_type": "eq.listing",
            "target": f"eq.{listing_id}",
            "enabled": "eq.true",
            "select": "*",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_watchlist(r) for r in resp.json()]

    async def matching_shops(
        self,
        marketplace: str,
        handle: str,
    ) -> list[Watchlist]:
        target = f"{marketplace}:{handle}".lower()
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_watchlists"
        params = {
            "watch_type": "eq.shop",
            "target": f"eq.{target}",
            "enabled": "eq.true",
            "select": "*",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_watchlist(r) for r in resp.json()]


# -----------------------------------------------------------------------------
# Alerts
# -----------------------------------------------------------------------------


class SupabaseAlertStore(_PostgrestBase, AlertStore):
    """spy_alerts CRUD over PostgREST."""

    async def create(self, alert: Alert) -> Alert:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_alerts"
        headers = {**self._headers, "Prefer": "return=representation"}
        payload = _serialize_alert(alert)
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "spy_alert_create_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )
            resp.raise_for_status()
        rows = resp.json()
        return _row_to_alert(rows[0]) if rows else alert

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        only_unread: bool = False,
    ) -> list[Alert]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_alerts"
        params: dict[str, str] = {
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
            "limit": str(limit),
        }
        if only_unread:
            params["status"] = "in.(pending,delivered,failed)"
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_alert(r) for r in resp.json()]

    async def mark_status(
        self,
        alert_id: str,
        user_id: str,
        status: AlertStatus,
    ) -> bool:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_alerts"
        params = {"id": f"eq.{alert_id}", "user_id": f"eq.{user_id}"}
        payload: dict[str, object] = {"status": status.value}
        if status == AlertStatus.READ:
            payload["read_at"] = datetime.now(UTC).isoformat()
        resp = await client.patch(
            url, params=params, headers=self._headers, json=payload
        )
        return resp.status_code < 400

    async def mark_delivered(
        self,
        alert_id: str,
        delivered_channels: list[AlertChannel],
    ) -> None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_alerts"
        params = {"id": f"eq.{alert_id}"}
        payload = {
            "channels_delivered": [c.value for c in delivered_channels],
            "status": (
                AlertStatus.DELIVERED.value
                if delivered_channels
                else AlertStatus.FAILED.value
            ),
            "delivered_at": (
                datetime.now(UTC).isoformat() if delivered_channels else None
            ),
        }
        await client.patch(url, params=params, headers=self._headers, json=payload)

    async def list_pending(self, *, limit: int = 100) -> list[Alert]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_alerts"
        params = {
            "status": "eq.pending",
            "select": "*",
            "order": "created_at.asc",
            "limit": str(limit),
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_alert(r) for r in resp.json()]


# -----------------------------------------------------------------------------
# API keys
# -----------------------------------------------------------------------------


class SupabaseApiKeyStore(_PostgrestBase):
    """spy_api_keys CRUD + raw-key resolution."""

    async def create(self, *, user_id: str, label: str) -> tuple[SpyApiKey, str]:
        raw = "smp_" + secrets.token_urlsafe(32)
        prefix = raw[:10]
        key_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

        key = SpyApiKey(
            id=str(uuid.uuid4()),
            user_id=user_id,
            label=label,
            prefix=prefix,
            scopes=["spy:read"],
            revoked=False,
            created_at=datetime.now(UTC),
        )

        client = await self._http()
        url = f"{self._url}/rest/v1/spy_api_keys"
        headers = {**self._headers, "Prefer": "return=representation"}
        payload = {
            "id": key.id,
            "user_id": key.user_id,
            "label": key.label,
            "prefix": key.prefix,
            "key_hash": key_hash,
            "scopes": key.scopes,
            "revoked": key.revoked,
            "created_at": key.created_at.isoformat(),
        }
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            resp.raise_for_status()
        return key, raw

    async def list_for_user(self, user_id: str) -> list[SpyApiKey]:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_api_keys"
        params = {
            "user_id": f"eq.{user_id}",
            "select": "*",
            "order": "created_at.desc",
        }
        resp = await client.get(url, params=params, headers=self._headers)
        resp.raise_for_status()
        return [_row_to_api_key(r) for r in resp.json()]

    async def revoke(self, key_id: str, user_id: str) -> bool:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_api_keys"
        params = {"id": f"eq.{key_id}", "user_id": f"eq.{user_id}"}
        resp = await client.patch(
            url, params=params, headers=self._headers, json={"revoked": True}
        )
        return resp.status_code < 400

    async def resolve(self, raw_key: str) -> SpyApiKey | None:
        h = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_api_keys"
        params = {
            "key_hash": f"eq.{h}",
            "revoked": "eq.false",
            "select": "*",
            "limit": "1",
        }
        try:
            resp = await client.get(url, params=params, headers=self._headers)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            logger.warning("spy_api_key_resolve_failed", error=str(e))
            return None
        if not rows:
            return None
        key = _row_to_api_key(rows[0])
        # Best-effort touch of last_used_at
        try:
            await client.patch(
                f"{self._url}/rest/v1/spy_api_keys",
                params={"id": f"eq.{key.id}"},
                headers=self._headers,
                json={"last_used_at": datetime.now(UTC).isoformat()},
            )
        except Exception:
            pass
        return key


# -----------------------------------------------------------------------------
# Serialization helpers
# -----------------------------------------------------------------------------


def _serialize_watchlist(w: Watchlist) -> dict[str, object]:
    return {
        "id": w.id,
        "user_id": w.user_id,
        "watch_type": w.watch_type.value,
        "target": w.target,
        "label": w.label,
        "triggers": [t.value for t in w.triggers],
        "channels": [
            {
                "channel": c.channel.value,
                "target": c.target,
                "enabled": c.enabled,
            }
            for c in w.channels
        ],
        "enabled": w.enabled,
        "created_at": w.created_at.isoformat(),
        "updated_at": w.updated_at.isoformat(),
    }


def _row_to_watchlist(row: dict[str, object]) -> Watchlist:
    channels_raw = row.get("channels") or []
    channels: list[AlertChannelConfig] = []
    if isinstance(channels_raw, list):
        for c in channels_raw:
            if not isinstance(c, dict):
                continue
            try:
                channels.append(
                    AlertChannelConfig(
                        channel=AlertChannel(c.get("channel", "in_app")),
                        target=c.get("target"),  # type: ignore[arg-type]
                        enabled=bool(c.get("enabled", True)),
                    )
                )
            except Exception:
                continue

    triggers_raw = row.get("triggers") or []
    triggers: list[AlertTrigger] = []
    for t in triggers_raw:
        try:
            triggers.append(AlertTrigger(t))
        except Exception:
            continue

    return Watchlist(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        watch_type=WatchType(str(row["watch_type"])),
        target=str(row["target"]),
        label=row.get("label"),  # type: ignore[arg-type]
        triggers=triggers,
        channels=channels,
        enabled=bool(row.get("enabled", True)),
        created_at=_dt(row.get("created_at")),
        updated_at=_dt(row.get("updated_at")),
    )


def _serialize_alert(a: Alert) -> dict[str, object]:
    return {
        "id": a.id,
        "user_id": a.user_id,
        "watchlist_id": a.watchlist_id,
        "trigger": a.trigger.value,
        "status": a.status.value,
        "headline": a.headline,
        "detail": a.detail,
        "payload": a.payload,
        "target_url": str(a.target_url) if a.target_url else None,
        "channels_attempted": [c.value for c in a.channels_attempted],
        "channels_delivered": [c.value for c in a.channels_delivered],
        "severity": a.severity,
        "created_at": a.created_at.isoformat(),
        "delivered_at": a.delivered_at.isoformat() if a.delivered_at else None,
        "read_at": a.read_at.isoformat() if a.read_at else None,
    }


def _row_to_alert(row: dict[str, object]) -> Alert:
    return Alert(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        watchlist_id=row.get("watchlist_id"),  # type: ignore[arg-type]
        trigger=AlertTrigger(str(row["trigger"])),
        status=AlertStatus(str(row.get("status") or "pending")),
        headline=str(row["headline"]),
        detail=row.get("detail"),  # type: ignore[arg-type]
        payload=row.get("payload") or {},  # type: ignore[arg-type]
        target_url=row.get("target_url"),  # type: ignore[arg-type]
        channels_attempted=[
            AlertChannel(c) for c in (row.get("channels_attempted") or []) if c
        ],
        channels_delivered=[
            AlertChannel(c) for c in (row.get("channels_delivered") or []) if c
        ],
        severity=int(row.get("severity") or 50),
        created_at=_dt(row.get("created_at")),
        delivered_at=(
            _dt(row["delivered_at"]) if row.get("delivered_at") else None
        ),
        read_at=_dt(row["read_at"]) if row.get("read_at") else None,
    )


def _row_to_api_key(row: dict[str, object]) -> SpyApiKey:
    return SpyApiKey(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        label=str(row["label"]),
        prefix=str(row["prefix"]),
        scopes=list(row.get("scopes") or ["spy:read"]),  # type: ignore[arg-type]
        revoked=bool(row.get("revoked", False)),
        last_used_at=(
            _dt(row["last_used_at"]) if row.get("last_used_at") else None
        ),
        created_at=_dt(row.get("created_at")),
    )


def _dt(raw: object) -> datetime:
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(UTC)
