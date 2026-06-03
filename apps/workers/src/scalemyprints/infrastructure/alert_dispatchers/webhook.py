"""
Webhook dispatcher — POSTs the alert JSON to a user-supplied URL.

We sign each payload with an HMAC-SHA256 header (`X-SMP-Signature`)
using the user's API key as the secret, so downstream consumers can
verify authenticity.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import TYPE_CHECKING

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import AlertChannel
from scalemyprints.domain.spy.watchlist_service import AlertDispatcher

if TYPE_CHECKING:
    from scalemyprints.domain.spy.watchlist_models import Alert, AlertChannelConfig

logger = get_logger(__name__)


class WebhookAlertDispatcher(AlertDispatcher):
    @property
    def channel(self) -> AlertChannel:
        return AlertChannel.WEBHOOK

    def __init__(
        self,
        *,
        signing_secret: str = "",
        timeout_seconds: float = 6.0,
    ) -> None:
        self._secret = signing_secret
        self._timeout = timeout_seconds

    async def deliver(
        self,
        alert: Alert,
        channel_config: AlertChannelConfig,
    ) -> bool:
        if not channel_config.target:
            return False

        body = {
            "id": alert.id,
            "trigger": alert.trigger.value,
            "headline": alert.headline,
            "detail": alert.detail,
            "severity": alert.severity,
            "created_at": alert.created_at.isoformat(),
            "payload": alert.payload,
        }
        encoded = json.dumps(body, separators=(",", ":")).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self._secret:
            sig = hmac.new(
                self._secret.encode("utf-8"),
                encoded,
                hashlib.sha256,
            ).hexdigest()
            headers["X-SMP-Signature"] = f"sha256={sig}"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                resp = await c.post(channel_config.target, content=encoded, headers=headers)
                if resp.status_code >= 400:
                    logger.warning(
                        "webhook_dispatch_failed",
                        status=resp.status_code,
                        target=channel_config.target,
                    )
                    return False
                return True
        except Exception as e:
            logger.warning(
                "webhook_dispatch_error",
                error=str(e),
                target=channel_config.target,
            )
            return False
