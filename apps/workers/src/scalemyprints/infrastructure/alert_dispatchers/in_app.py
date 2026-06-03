"""
In-app dispatcher — the alert is already persisted by AlertStore.create.
"Delivery" here just means marking the alert visible in the user's
in-app feed. We use this as the always-on baseline channel.
"""

from __future__ import annotations

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import Alert, AlertChannel, AlertChannelConfig
from scalemyprints.domain.spy.watchlist_service import AlertDispatcher

logger = get_logger(__name__)


class InAppAlertDispatcher(AlertDispatcher):
    @property
    def channel(self) -> AlertChannel:
        return AlertChannel.IN_APP

    async def deliver(
        self,
        alert: Alert,
        channel_config: AlertChannelConfig,
    ) -> bool:
        # No-op — the alert row is already in the user's in-app feed.
        # We still log so ops can audit dispatcher activity.
        logger.info(
            "in_app_alert_delivered",
            alert_id=alert.id,
            user_id=alert.user_id,
            trigger=alert.trigger.value,
        )
        return True
