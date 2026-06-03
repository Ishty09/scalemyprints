"""
Watchlist + Alert orchestrator.

Surface:
- create / list / update / delete watchlists per user
- evaluate(): given a recent set of velocity signals + viral signals,
  fan out to matching watchlists and queue alerts for delivery
- deliver(): pop pending alerts and dispatch via configured channels

Storage is a Protocol port — `WatchlistStore`. Memory and Supabase
implementations live in `infrastructure/spy_storage/`.

Channels are also Protocols — `AlertDispatcher`. The container wires
in concrete dispatchers based on Settings (Resend for email, Slack
incoming webhook, custom POST URL, in-app row).

We NEVER raise — all errors land in the Alert's status field.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import (
    Alert,
    AlertChannel,
    AlertChannelConfig,
    AlertStatus,
    AlertTrigger,
    Watchlist,
    WatchType,
)

if TYPE_CHECKING:
    from scalemyprints.domain.spy.models import VelocitySignal, ViralSignal

logger = get_logger(__name__)


# -----------------------------------------------------------------------------
# Ports
# -----------------------------------------------------------------------------


@runtime_checkable
class WatchlistStore(Protocol):
    async def create(self, watchlist: Watchlist) -> Watchlist: ...

    async def get(self, watchlist_id: str, user_id: str) -> Watchlist | None: ...

    async def list_for_user(self, user_id: str) -> list[Watchlist]: ...

    async def update(self, watchlist: Watchlist) -> Watchlist: ...

    async def delete(self, watchlist_id: str, user_id: str) -> bool: ...

    async def matching_phrases(self, phrase: str) -> list[Watchlist]: ...
    """Find watchlists whose `target` matches the (normalized) phrase."""

    async def matching_listings(self, listing_id: str) -> list[Watchlist]: ...

    async def matching_shops(
        self,
        marketplace: str,
        handle: str,
    ) -> list[Watchlist]: ...


@runtime_checkable
class AlertStore(Protocol):
    async def create(self, alert: Alert) -> Alert: ...

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 50,
        only_unread: bool = False,
    ) -> list[Alert]: ...

    async def mark_status(
        self,
        alert_id: str,
        user_id: str,
        status: AlertStatus,
    ) -> bool: ...

    async def mark_delivered(
        self,
        alert_id: str,
        delivered_channels: list[AlertChannel],
    ) -> None: ...

    async def list_pending(
        self,
        *,
        limit: int = 100,
    ) -> list[Alert]:
        """Return up to `limit` alerts in status=pending across all users.

        Used by the cron-driven dispatcher to fan alerts out through
        their configured channels (Slack / webhook / email).
        """
        ...


@runtime_checkable
class AlertDispatcher(Protocol):
    @property
    def channel(self) -> AlertChannel: ...

    async def deliver(
        self,
        alert: Alert,
        channel_config: AlertChannelConfig,
    ) -> bool:
        """Return True on success. Never raise."""
        ...


# -----------------------------------------------------------------------------
# Result types
# -----------------------------------------------------------------------------


class EvaluationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
    watchlists_checked: int = Field(ge=0)
    alerts_created: int = Field(ge=0)


class DeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempted: int = Field(ge=0)
    delivered: int = Field(ge=0)
    failed: int = Field(ge=0)
    by_channel: dict[str, int] = Field(default_factory=dict)


# -----------------------------------------------------------------------------
# Service
# -----------------------------------------------------------------------------


class WatchlistService:
    """CRUD + evaluate + deliver for watchlists/alerts."""

    def __init__(
        self,
        *,
        watchlist_store: WatchlistStore,
        alert_store: AlertStore,
        dispatchers: list[AlertDispatcher],
    ) -> None:
        self._w = watchlist_store
        self._a = alert_store
        self._dispatchers = {d.channel: d for d in dispatchers}

    # ----- CRUD ------------------------------------------------------

    async def create(
        self,
        *,
        user_id: str,
        watch_type: WatchType,
        target: str,
        label: str | None,
        triggers: list[AlertTrigger],
        channels: list[AlertChannelConfig],
    ) -> Watchlist:
        now = datetime.now(UTC)
        w = Watchlist(
            id=str(uuid.uuid4()),
            user_id=user_id,
            watch_type=watch_type,
            target=target.strip(),
            label=label,
            triggers=triggers,
            channels=channels,
            enabled=True,
            created_at=now,
            updated_at=now,
        )
        return await self._w.create(w)

    async def list_for_user(self, user_id: str) -> list[Watchlist]:
        return await self._w.list_for_user(user_id)

    async def delete(self, watchlist_id: str, user_id: str) -> bool:
        return await self._w.delete(watchlist_id, user_id)

    # ----- Evaluate (called by cron) ---------------------------------

    async def evaluate(
        self,
        *,
        velocity_signals: list[VelocitySignal] | None = None,
        viral_signals: list[ViralSignal] | None = None,
    ) -> EvaluationResult:
        started = datetime.now(UTC)
        start_mono = time.monotonic()

        watchlists_checked = 0
        alerts_created = 0

        # ----- Velocity spike → SHOP / LISTING / PHRASE watchlists -----
        for vs in velocity_signals or []:
            watchlists_checked += 1
            matches = await self._w.matching_listings(vs.listing_id)
            for w in matches:
                if not w.enabled or AlertTrigger.VELOCITY_SPIKE not in w.triggers:
                    continue
                alert = self._build_alert_for_velocity(w, vs)
                await self._a.create(alert)
                alerts_created += 1

        # ----- Viral signals → PHRASE / VIRAL_CATEGORY watchlists ------
        for vs2 in viral_signals or []:
            watchlists_checked += 1
            matches = await self._w.matching_phrases(vs2.phrase)
            for w in matches:
                if not w.enabled or AlertTrigger.VIRAL_HIT not in w.triggers:
                    continue
                alert = self._build_alert_for_viral(w, vs2)
                await self._a.create(alert)
                alerts_created += 1

        return EvaluationResult(
            started_at=started,
            completed_at=datetime.now(UTC),
            duration_ms=int((time.monotonic() - start_mono) * 1000),
            watchlists_checked=watchlists_checked,
            alerts_created=alerts_created,
        )

    # ----- Deliver (called by cron, fans out to channels) ------------

    async def deliver_pending(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
    ) -> DeliveryResult:
        """
        Pop pending alerts and fan out through each watchlist's configured
        channels. Called by the cron `/_internal/deliver-alerts` route.

        `user_id` is reserved for the per-user dashboard "send now"
        button — Phase 4.7 ignores it and dispatches across all users.
        """
        pending = await self._a.list_pending(limit=limit)

        attempted_total = 0
        delivered_total = 0
        failed_total = 0
        by_channel: dict[str, int] = {}

        for alert in pending:
            updated = await self.deliver_now(alert)
            attempted_total += len(updated.channels_attempted)
            delivered_total += len(updated.channels_delivered)
            if not updated.channels_delivered:
                failed_total += 1
            for ch in updated.channels_delivered:
                by_channel[ch.value] = by_channel.get(ch.value, 0) + 1

        return DeliveryResult(
            attempted=attempted_total,
            delivered=delivered_total,
            failed=failed_total,
            by_channel=by_channel,
        )

    async def deliver_now(self, alert: Alert) -> Alert:
        """Synchronously dispatch a single alert across all channels."""
        delivered: list[AlertChannel] = []
        attempted: list[AlertChannel] = []
        # We need the source watchlist to know channels; if not given,
        # default to IN_APP only.
        wl_channels: list[AlertChannelConfig] = []
        if alert.watchlist_id:
            wl = await self._w.get(alert.watchlist_id, alert.user_id)
            if wl is not None:
                wl_channels = wl.channels
        if not wl_channels:
            wl_channels = [AlertChannelConfig(channel=AlertChannel.IN_APP)]

        for cfg in wl_channels:
            if not cfg.enabled:
                continue
            dispatcher = self._dispatchers.get(cfg.channel)
            if dispatcher is None:
                continue
            attempted.append(cfg.channel)
            try:
                ok = await dispatcher.deliver(alert, cfg)
            except Exception as e:
                logger.warning(
                    "alert_dispatcher_failed",
                    channel=cfg.channel.value,
                    error=str(e),
                )
                ok = False
            if ok:
                delivered.append(cfg.channel)

        await self._a.mark_delivered(alert.id, delivered)
        return alert.model_copy(
            update={
                "channels_attempted": attempted,
                "channels_delivered": delivered,
                "status": AlertStatus.DELIVERED if delivered else AlertStatus.FAILED,
                "delivered_at": datetime.now(UTC) if delivered else None,
            }
        )

    # ----- Helpers ---------------------------------------------------

    def _build_alert_for_velocity(
        self,
        w: Watchlist,
        vs: VelocitySignal,
    ) -> Alert:
        now = datetime.now(UTC)
        severity = 60 + min(40, max(0, int((vs.z_score - 2.5) * 10)))
        return Alert(
            id=str(uuid.uuid4()),
            user_id=w.user_id,
            watchlist_id=w.id,
            trigger=AlertTrigger.VELOCITY_SPIKE,
            status=AlertStatus.PENDING,
            headline=f"Velocity spike on {w.label or w.target}",
            detail=vs.note,
            payload=vs.model_dump(mode="json"),
            severity=severity,
            created_at=now,
        )

    def _build_alert_for_viral(
        self,
        w: Watchlist,
        vs: object,  # ViralSignal
    ) -> Alert:
        from scalemyprints.domain.spy.models import ViralSignal  # noqa: PLC0415

        assert isinstance(vs, ViralSignal)
        now = datetime.now(UTC)
        return Alert(
            id=str(uuid.uuid4()),
            user_id=w.user_id,
            watchlist_id=w.id,
            trigger=AlertTrigger.VIRAL_HIT,
            status=AlertStatus.PENDING,
            headline=f"Viral hit: {vs.phrase[:80]}",
            detail=vs.note,
            payload=vs.model_dump(mode="json"),
            severity=max(40, vs.pod_readiness_score),
            created_at=now,
        )
