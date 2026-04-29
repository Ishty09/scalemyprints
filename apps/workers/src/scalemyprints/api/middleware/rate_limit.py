"""
Rate limiting.

Token-bucket limiter keyed by user ID (or IP for anonymous). Phase A is
in-memory per process; Phase B swaps to Redis for multi-instance coherence.

Usage in routes:
    await rate_limiter.check(key=user.id, limit=60, window_seconds=60)

Raises RateLimitedError if exceeded.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from functools import lru_cache

from fastapi import Request

from scalemyprints.core.errors import RateLimitedError
from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class _Bucket:
    """A sliding-window counter for a single key."""

    count: int = 0
    window_start: float = field(default_factory=time.monotonic)


class RateLimiter:
    """
    Simple fixed-window rate limiter.

    Not cryptographically accurate at window boundaries but fine for
    best-effort abuse prevention. Replace with Redis-backed token bucket
    in Phase B when we need multi-process coherence.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = asyncio.Lock()

    async def check(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> None:
        """
        Increment the counter for `key`. Raises RateLimitedError if
        `limit` calls have already been made in the current window.
        """
        if limit <= 0:
            return  # unlimited

        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None or now - bucket.window_start >= window_seconds:
                # New window
                self._buckets[key] = _Bucket(count=1, window_start=now)
                return

            bucket.count += 1
            if bucket.count > limit:
                retry_after = int(window_seconds - (now - bucket.window_start)) + 1
                logger.info(
                    "rate_limit_exceeded",
                    key=key,
                    limit=limit,
                    window_seconds=window_seconds,
                    retry_after_seconds=retry_after,
                )
                raise RateLimitedError(retry_after_seconds=retry_after)

    async def reset(self, key: str) -> None:
        """Test helper."""
        async with self._lock:
            self._buckets.pop(key, None)


@lru_cache(maxsize=1)
def get_rate_limiter() -> RateLimiter:
    """Process-wide singleton."""
    return RateLimiter()


def client_ip(request: Request) -> str:
    """
    Extract client IP for anonymous rate-limit keying.

    Prefers X-Forwarded-For (set by trusted proxies), falls back to direct.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take first IP in the chain
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"
