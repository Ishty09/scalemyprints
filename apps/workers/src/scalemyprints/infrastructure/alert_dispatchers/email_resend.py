"""
Email dispatcher — uses the Resend HTTP API.

Requires `RESEND_API_KEY` to be configured. Falls back to a no-op
(returns False) if missing.
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


class ResendEmailAlertDispatcher(AlertDispatcher):
    @property
    def channel(self) -> AlertChannel:
        return AlertChannel.EMAIL

    def __init__(self, *, timeout_seconds: float = 8.0) -> None:
        self._timeout = timeout_seconds

    async def deliver(
        self,
        alert: Alert,
        channel_config: AlertChannelConfig,
    ) -> bool:
        if not channel_config.target:
            return False

        settings = get_settings()
        api_key = settings.resend_api_key.get_secret_value()
        if not api_key:
            logger.info("resend_api_key_unconfigured")
            return False

        web_app = settings.web_app_url.rstrip("/")
        html_body = _render_html(alert, web_app)

        payload = {
            "from": f"{settings.resend_from_name} <{settings.resend_from_email}>",
            "to": [channel_config.target],
            "subject": alert.headline[:200],
            "html": html_body,
            "text": alert.detail or alert.headline,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as c:
                resp = await c.post(
                    "https://api.resend.com/emails",
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "resend_dispatch_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
                    return False
                return True
        except Exception as e:
            logger.warning("resend_dispatch_error", error=str(e))
            return False


def _render_html(alert: Alert, web_app: str) -> str:
    severity_color = (
        "#10b981" if alert.severity < 40 else "#f59e0b" if alert.severity < 75 else "#ef4444"
    )
    return f"""<!doctype html>
<html><body style="font-family: -apple-system, sans-serif; padding: 24px; color: #0f172a;">
  <h2 style="margin: 0 0 8px 0;">🔭 {alert.headline}</h2>
  <p style="color: #64748b; font-size: 13px; margin: 0 0 16px 0;">
    Trigger: <code>{alert.trigger.value}</code> · Severity: <strong style="color: {severity_color}">{alert.severity}/100</strong>
  </p>
  {f'<p>{alert.detail}</p>' if alert.detail else ''}
  <p style="margin-top: 24px;">
    <a href="{web_app}/dashboard/spy" style="display: inline-block; background: #0d9488; color: #fff; padding: 10px 16px; border-radius: 8px; text-decoration: none; font-weight: 600;">
      Open in Spy →
    </a>
  </p>
</body></html>"""
