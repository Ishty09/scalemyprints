"""Watchlist + Alert engine."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.spy.enums import VelocityClass
from scalemyprints.domain.spy.models import VelocitySignal, ViralSignal
from scalemyprints.domain.spy.watchlist_models import (
    AlertChannel,
    AlertChannelConfig,
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
    def __init__(self, channel: AlertChannel) -> None:
        self._channel = channel
        self.calls: list[str] = []

    @property
    def channel(self) -> AlertChannel:
        return self._channel

    async def deliver(self, alert, channel_config) -> bool:
        self.calls.append(alert.id)
        return True


def _signal(listing_id: str) -> VelocitySignal:
    return VelocitySignal(
        listing_id=listing_id,
        captured_at=datetime.now(UTC),
        velocity_class=VelocityClass.SPIKING,
        z_score=3.4,
        sales_baseline=2.0,
        sales_current=20.0,
        confidence=0.9,
        note="spiking",
    )


def _viral(phrase: str, score: int = 70) -> ViralSignal:
    from scalemyprints.domain.spy.enums import ViralSource  # noqa: PLC0415

    return ViralSignal(
        source=ViralSource.REDDIT,
        phrase=phrase,
        detected_at=datetime.now(UTC),
        engagement=100,
        momentum_score=50,
        pod_readiness_score=score,
        existing_pod_count=0,
        suggested_styles=[],
    )


@pytest.fixture
def svc() -> WatchlistService:
    return WatchlistService(
        watchlist_store=MemoryWatchlistStore(),
        alert_store=MemoryAlertStore(),
        dispatchers=[InAppAlertDispatcher()],
    )


@pytest.mark.asyncio
async def test_crud_round_trip(svc: WatchlistService) -> None:
    created = await svc.create(
        user_id="u1",
        watch_type=WatchType.PHRASE,
        target="vintage motorcycle",
        label="My niche",
        triggers=[AlertTrigger.VIRAL_HIT],
        channels=[AlertChannelConfig(channel=AlertChannel.IN_APP)],
    )
    assert created.id
    rows = await svc.list_for_user("u1")
    assert len(rows) == 1
    assert rows[0].target == "vintage motorcycle"

    deleted = await svc.delete(created.id, "u1")
    assert deleted is True

    rows_after = await svc.list_for_user("u1")
    assert rows_after == []


@pytest.mark.asyncio
async def test_velocity_signal_triggers_alert(svc: WatchlistService) -> None:
    wl = await svc.create(
        user_id="u2",
        watch_type=WatchType.LISTING,
        target="LISTING-42",
        label="Star listing",
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[AlertChannelConfig(channel=AlertChannel.IN_APP)],
    )
    result = await svc.evaluate(velocity_signals=[_signal("LISTING-42")])
    assert result.alerts_created == 1

    alerts = await svc._a.list_for_user("u2")
    assert len(alerts) == 1
    assert alerts[0].trigger == AlertTrigger.VELOCITY_SPIKE
    assert alerts[0].watchlist_id == wl.id


@pytest.mark.asyncio
async def test_viral_signal_matches_phrase_watchlist(svc: WatchlistService) -> None:
    await svc.create(
        user_id="u3",
        watch_type=WatchType.PHRASE,
        target="vintage",
        label=None,
        triggers=[AlertTrigger.VIRAL_HIT],
        channels=[AlertChannelConfig(channel=AlertChannel.IN_APP)],
    )
    result = await svc.evaluate(
        viral_signals=[_viral("Cool VINTAGE motorcycle vibes")],
    )
    assert result.alerts_created == 1


@pytest.mark.asyncio
async def test_disabled_watchlist_does_not_fire(svc: WatchlistService) -> None:
    wl = await svc.create(
        user_id="u4",
        watch_type=WatchType.LISTING,
        target="L9",
        label=None,
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[],
    )
    # Disable via direct mutation in the store
    await svc._w.update(wl.model_copy(update={"enabled": False}))
    result = await svc.evaluate(velocity_signals=[_signal("L9")])
    assert result.alerts_created == 0


@pytest.mark.asyncio
async def test_dispatch_records_delivered_channels() -> None:
    dispatcher = _CountingDispatcher(AlertChannel.WEBHOOK)
    svc = WatchlistService(
        watchlist_store=MemoryWatchlistStore(),
        alert_store=MemoryAlertStore(),
        dispatchers=[InAppAlertDispatcher(), dispatcher],
    )
    wl = await svc.create(
        user_id="u5",
        watch_type=WatchType.LISTING,
        target="L99",
        label=None,
        triggers=[AlertTrigger.VELOCITY_SPIKE],
        channels=[
            AlertChannelConfig(channel=AlertChannel.IN_APP),
            AlertChannelConfig(channel=AlertChannel.WEBHOOK, target="https://example/hook"),
        ],
    )
    await svc.evaluate(velocity_signals=[_signal("L99")])
    [alert] = await svc._a.list_for_user("u5")
    delivered = await svc.deliver_now(alert)
    assert AlertChannel.IN_APP in delivered.channels_delivered
    assert AlertChannel.WEBHOOK in delivered.channels_delivered
    assert dispatcher.calls == [alert.id]
