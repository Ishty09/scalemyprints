"""
In-memory implementations of WatchlistStore + AlertStore + ApiKeyStore.

Used in tests and as a dev fallback when Supabase isn't configured.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from scalemyprints.domain.spy.watchlist_models import (
    Alert,
    AlertChannel,
    AlertStatus,
    SpyApiKey,
    Watchlist,
    WatchType,
)
from scalemyprints.domain.spy.watchlist_service import (
    AlertStore,
    WatchlistStore,
)


class MemoryWatchlistStore(WatchlistStore):
    """Process-local watchlist store."""

    def __init__(self) -> None:
        self._rows: dict[str, Watchlist] = {}

    async def create(self, watchlist: Watchlist) -> Watchlist:
        self._rows[watchlist.id] = watchlist
        return watchlist

    async def get(self, watchlist_id: str, user_id: str) -> Watchlist | None:
        row = self._rows.get(watchlist_id)
        if row is None or row.user_id != user_id:
            return None
        return row

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        return [w for w in self._rows.values() if w.user_id == user_id]

    async def update(self, watchlist: Watchlist) -> Watchlist:
        self._rows[watchlist.id] = watchlist
        return watchlist

    async def delete(self, watchlist_id: str, user_id: str) -> bool:
        row = self._rows.get(watchlist_id)
        if row is None or row.user_id != user_id:
            return False
        del self._rows[watchlist_id]
        return True

    async def matching_phrases(self, phrase: str) -> list[Watchlist]:
        # `phrase` is the candidate text we just observed (e.g., a viral
        # signal title). It matches a watchlist when the watchlist's
        # `target` (the keyword being watched) appears inside `phrase`.
        norm_observed = (phrase or "").strip().lower()
        return [
            w
            for w in self._rows.values()
            if w.enabled
            and w.watch_type in (WatchType.PHRASE, WatchType.VIRAL_CATEGORY)
            and w.target.strip().lower() in norm_observed
        ]

    async def matching_listings(self, listing_id: str) -> list[Watchlist]:
        return [
            w
            for w in self._rows.values()
            if w.enabled and w.watch_type == WatchType.LISTING and w.target == listing_id
        ]

    async def matching_shops(self, marketplace: str, handle: str) -> list[Watchlist]:
        target = f"{marketplace}:{handle}".lower()
        return [
            w
            for w in self._rows.values()
            if w.enabled
            and w.watch_type == WatchType.SHOP
            and w.target.lower() == target
        ]

    def clear(self) -> None:
        self._rows.clear()


class MemoryAlertStore(AlertStore):
    """Process-local alert store."""

    def __init__(self) -> None:
        self._rows: dict[str, Alert] = {}

    async def create(self, alert: Alert) -> Alert:
        self._rows[alert.id] = alert
        return alert

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        only_unread: bool = False,
    ) -> list[Alert]:
        rows = [r for r in self._rows.values() if r.user_id == user_id]
        if only_unread:
            rows = [
                r
                for r in rows
                if r.status not in (AlertStatus.READ, AlertStatus.DISMISSED)
            ]
        rows.sort(key=lambda r: r.created_at, reverse=True)
        return rows[:limit]

    async def mark_status(
        self,
        alert_id: str,
        user_id: str,
        status: AlertStatus,
    ) -> bool:
        row = self._rows.get(alert_id)
        if row is None or row.user_id != user_id:
            return False
        now = datetime.now(UTC)
        updates: dict[str, object] = {"status": status}
        if status == AlertStatus.READ:
            updates["read_at"] = now
        self._rows[alert_id] = row.model_copy(update=updates)
        return True

    async def mark_delivered(
        self,
        alert_id: str,
        delivered_channels: list[AlertChannel],
    ) -> None:
        row = self._rows.get(alert_id)
        if row is None:
            return
        self._rows[alert_id] = row.model_copy(
            update={
                "channels_delivered": delivered_channels,
                "status": (
                    AlertStatus.DELIVERED if delivered_channels else AlertStatus.FAILED
                ),
                "delivered_at": datetime.now(UTC) if delivered_channels else None,
            }
        )

    async def list_pending(self, *, limit: int = 100) -> list[Alert]:
        rows = [r for r in self._rows.values() if r.status == AlertStatus.PENDING]
        rows.sort(key=lambda r: r.created_at)
        return rows[:limit]

    def clear(self) -> None:
        self._rows.clear()

    def size(self) -> int:
        return len(self._rows)


# -----------------------------------------------------------------------------
# API key store + helpers
# -----------------------------------------------------------------------------


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns (clear_text, prefix, hash). The clear text is shown to the
    user exactly once; we persist only the hash.
    """
    import hashlib  # noqa: PLC0415

    raw = "smp_" + secrets.token_urlsafe(32)
    prefix = raw[:10]
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, prefix, h


class MemoryApiKeyStore:
    """Process-local store of SpyApiKey rows + their hashes."""

    def __init__(self) -> None:
        self._by_id: dict[str, SpyApiKey] = {}
        self._hash_to_id: dict[str, str] = {}

    async def create(self, *, user_id: str, label: str) -> tuple[SpyApiKey, str]:
        raw, prefix, h = generate_api_key()
        import uuid  # noqa: PLC0415

        key = SpyApiKey(
            id=str(uuid.uuid4()),
            user_id=user_id,
            label=label,
            prefix=prefix,
            scopes=["spy:read"],
            revoked=False,
            created_at=datetime.now(UTC),
        )
        self._by_id[key.id] = key
        self._hash_to_id[h] = key.id
        return key, raw

    async def list_for_user(self, user_id: str) -> list[SpyApiKey]:
        return [k for k in self._by_id.values() if k.user_id == user_id]

    async def revoke(self, key_id: str, user_id: str) -> bool:
        key = self._by_id.get(key_id)
        if key is None or key.user_id != user_id:
            return False
        self._by_id[key_id] = key.model_copy(update={"revoked": True})
        return True

    async def resolve(self, raw_key: str) -> SpyApiKey | None:
        import hashlib  # noqa: PLC0415

        h = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        key_id = self._hash_to_id.get(h)
        if not key_id:
            return None
        key = self._by_id.get(key_id)
        if key is None or key.revoked:
            return None
        return key
