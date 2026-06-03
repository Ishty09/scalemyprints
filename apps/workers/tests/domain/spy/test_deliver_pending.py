"""Phase 4.7 — cron-driven alert delivery loop."""

from __future__ import annotations

import pytest

from scalemyprints.domain.spy.enums import VelocityClass
from scalemyprints.domain.spy.models import VelocitySignal
from scalemyprints.domain.spy.watchlist_models import (
    AlertChannel,
    AlertChannelConfig,
    AlertStatus,
    AlertTrigger,
    WatchType,
)
from scalemyprints.domain.spy.watchlist_service import (
    AlertDispatcher,
    WatchlistService,
)
from scalemyprints.infrastructure.alert_dispatchers.in_app import InAppAlertDispatcher
from scalemyprints.infrastructure.spy_storage.memory_watchlist_store import (
    MemoryAlertStore,
    MemoryWatchlistStore,
)


class _CountingDispatcher(AlertDispatcher):
    def __init__(self, ch: AlertChannel, succeed: bool = True) -> None:
        self._ch = ch
        self._succeed = succeed
        self.calls: int = 0

    @property
    def channel(self) -> AlertChannel:
        return self._ch

    async def deliver(self, alert, channel_config) -> bool:
        self.calls += 1
        return self._succeed


def _signal(listing_id: str) -> VelocitySignal:
    from datetime import UTC, datetime  # noqa: PLC0415

    return VelocitySignal(
        listing_id=listing_id,
        captured_at=datetime.now(UTC),
        velocity_class=VelocityClass.SPIKING,
        z_score=3.0,
        sales_baseline=2.0,
        sales_current=15.0,
        confidence=0.8,
    )


@pytest.mark.asyncio
async def test_deliver_pending_dispatches_alerts_through_channels() -> None:
    in_app = InAppAlertDispatcher()
    webhook = _CountingDispatcher(AlertChannel.WEBHOOK)

    svc = WatchlistService(
        watchlist_store=MemoryWatchlistStore(),
        alert_store=MemoryAlertStore(),
        dispatchers=[in_app, webhook],
    )
    await svc.create(
        user_id="u1",
        watch_type=WatchType.LISTING,
        target="L1",
        label="Spike watch",
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[
            AlertChannelConfig(channel=AlertChannel.IN_APP),
            AlertChannelConfig(
                channel=AlertChannel.WEBHOOK,
                target="https://hook.example.com",
            ),
        ],
    )
    await svc.evaluate(velocity_signals=[_signal("L1")])

    # One pending alert should now exist.
    pending = await svc._a.list_pending()
    assert len(pending) == 1
    assert pending[0].status == AlertStatus.PENDING

    result = await svc.deliver_pending(limit=10)
    assert result.attempted == 2          # in_app + webhook attempted
    assert result.delivered == 2          # both succeed
    assert result.failed == 0
    assert result.by_channel.get("webhook") == 1
    assert webhook.calls == 1

    # Alert is now delivered (no longer pending).
    pending_after = await svc._a.list_pending()
    assert pending_after == []


@pytest.mark.asyncio
async def test_deliver_pending_records_failed_when_no_channel_succeeds() -> None:
    failing = _CountingDispatcher(AlertChannel.WEBHOOK, succeed=False)
    svc = WatchlistService(
        watchlist_store=MemoryWatchlistStore(),
        alert_store=MemoryAlertStore(),
        dispatchers=[failing],
    )
    await svc.create(
        user_id="u2",
        watch_type=WatchType.LISTING,
        target="L2",
        label=None,
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[
            AlertChannelConfig(
                channel=AlertChannel.WEBHOOK,
                target="https://broken.example.com",
            ),
        ],
    )
    await svc.evaluate(velocity_signals=[_signal("L2")])

    result = await svc.deliver_pending(limit=10)
    assert result.attempted == 1
    assert result.delivered == 0
    assert result.failed == 1


@pytest.mark.asyncio
async def test_deliver_pending_empty_when_no_pending_alerts() -> None:
    svc = WatchlistService(
        watchlist_store=MemoryWatchlistStore(),
        alert_store=MemoryAlertStore(),
        dispatchers=[InAppAlertDispatcher()],
    )
    result = await svc.deliver_pending(limit=10)
    assert result.attempted == 0
    assert result.delivered == 0
    assert result.failed == 0
