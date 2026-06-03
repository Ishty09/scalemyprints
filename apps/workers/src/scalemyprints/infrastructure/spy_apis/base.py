"""
Shared HTTP plumbing for Spy adapters.

Adapters layer their own scraping logic on top of:
- `make_async_client(...)` — curl_cffi-backed AsyncSession when
  available (TLS fingerprint spoofing for anti-bot), httpx fallback
- `RotatingHeaderPool` — random UA / Accept-Language per request
- `with_retry` — tenacity-backed retry wrapper
- `safe_decimal` / `safe_int` — defensive parsing helpers

Anti-bot strategy (Phase 1):
  1. curl_cffi impersonate=chrome124 (TLS + JA3 fingerprint)
  2. Rotating UA pool (10 desktop UAs)
  3. Tenacity retry: 3 attempts, exponential backoff
  4. Optional residential proxy (env: SPY_PROXY_URL)
  5. Apify fallback (existing tokens) when direct scrape blocked
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, TypeVar

from scalemyprints.core.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)


# Rotating UA pool — Chrome / Firefox / Safari latest desktop releases.
_USER_AGENTS = [
    # Chrome 124 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Firefox 125 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Firefox 125 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
    # Safari 17 Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    # Edge 124 Win
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
    # Chrome 124 Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    # Chrome 124 Android
    "Mozilla/5.0 (Linux; Android 13; SM-G998U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
    # Safari iOS 17
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    # Firefox 125 Linux
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]

_ACCEPT_LANGUAGES = [
    "en-US,en;q=0.9",
    "en-US,en;q=0.8,en-GB;q=0.6",
    "en-GB,en;q=0.9",
    "en-CA,en;q=0.9,fr-CA;q=0.7,fr;q=0.5",
    "en-AU,en;q=0.9",
]


def rotating_headers(*, accept_html: bool = True) -> dict[str, str]:
    """Build a fresh request header set with rotated UA + language."""
    ua = random.choice(_USER_AGENTS)
    accept = (
        "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
        if accept_html
        else "application/json,text/plain,*/*"
    )
    return {
        "User-Agent": ua,
        "Accept": accept,
        "Accept-Language": random.choice(_ACCEPT_LANGUAGES),
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Sec-Fetch-Dest": "document" if accept_html else "empty",
        "Sec-Fetch-Mode": "navigate" if accept_html else "cors",
        "Sec-Fetch-Site": "none",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


T = TypeVar("T")


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
) -> T:
    """
    Lightweight retry wrapper with exponential backoff.

    Tenacity is used elsewhere, but its decorator API doesn't compose
    well with closures inside adapter methods. This is a tiny inline
    alternative for the Spy hot paths.
    """
    import asyncio

    last: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception as e:
            last = e
            if attempt >= attempts:
                raise
            delay = base_delay * (2 ** (attempt - 1)) * (0.8 + 0.4 * random.random())
            logger.info("spy_retry", attempt=attempt, delay_ms=int(delay * 1000), error=str(e))
            await asyncio.sleep(delay)
    if last:
        raise last
    raise RuntimeError("unreachable")


def safe_int(value: object, default: int | None = None) -> int | None:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value: object, default: float | None = None) -> float | None:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
