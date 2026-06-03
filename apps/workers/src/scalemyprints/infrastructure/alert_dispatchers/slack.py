"""
Slack dispatcher — posts to a user-supplied Slack incoming webhook.

Each alert renders as a Block Kit payload with header + context + a
"View in dashboard" button.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from scalemyprints.core.config import get_settings
from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import AlertChannel
from scalemyprints.domain.spy.watchlist_service import AlertDispatcher

if TYPE_CHECKING:
    from scalemyprints.domain.spy.watchlist_models import Alert, AlertChannelConfig

logger = get_logger(__name__)


class SlackAlertDispatcher(AlertDispatcher):
    @property
    def channel(self) -> AlertChannel:
        return AlertChannel.SLACK

    def __init__(self, *, timeout_seconds: float = 6.0) -> None:
        self._timeout = timeout_seconds

    async def deliver(
        self,
        alert: Alert,
        channel_config: AlertChannelConfig,
    ) -> bool:
        if not channel_config.target:
            return False
        settings = get_settings()
        web_app = settings.web_app_url.rstrip("/")

        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"🔭 {alert.headline}"[:150],
                    },
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Trigger:* `{alert.trigger.value}` · *Severity:* {alert.severity}/100",
                        }
                    ],
                },
                *(
                    [
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": alert.detail or "—"},
                        }
                    ]
                    if alert.detail
                    else []
                ),
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Open in Spy"},
                            "url": f"{web_app}/dashboard/spy",
                        }
                    ],
                },
            ],
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                resp = await c.post(channel_config.target, json=payload)
                if resp.status_code >= 400:
                    logger.warning(
                        "slack_dispatch_failed",
                        status=resp.status_code,
                    )
                    return False
                return True
        except Exception as e:
            logger.warning("slack_dispatch_error", error=str(e))
            return False
