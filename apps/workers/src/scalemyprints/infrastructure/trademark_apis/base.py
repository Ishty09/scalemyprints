"""
Shared HTTP infrastructure for trademark API adapters.

Provides:
- A factory for configured httpx.AsyncClient instances
- A retry policy using tenacity (exponential backoff, retries on 5xx/timeouts)
- A common duration timer utility

All adapters use these primitives — never create raw httpx clients.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

DEFAULT_USER_AGENT = "ScaleMyPrints/0.1 (research)"
DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5.0

# Exceptions that are worth retrying — transient network/server failures only.
# NOT retried: 4xx client errors (they won't get better by retrying).
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.WriteTimeout,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


class HttpClientFactory:
    """
    Builds pre-configured httpx.AsyncClient instances.

    Centralizing client creation lets us tune timeouts, User-Agent, and
    proxy settings in one place.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        connect_timeout_seconds: float = DEFAULT_CONNECT_TIMEOUT_SECONDS,
    ) -> None:
        self._user_agent = user_agent
        self._timeout = httpx.Timeout(
            timeout=timeout_seconds,
            connect=connect_timeout_seconds,
        )

    def build(self, base_url: str, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
        """Construct a new client bound to the given base URL."""
        final_headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            final_headers.update(headers)

        return httpx.AsyncClient(
            base_url=base_url,
            headers=final_headers,
            timeout=self._timeout,
            follow_redirects=True,
            # Conservative pool: trademark APIs have rate limits
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )


# -----------------------------------------------------------------------------
# Retry policy
# -----------------------------------------------------------------------------


def build_retry_policy(
    *,
    max_attempts: int = 3,
    min_wait_seconds: float = 0.5,
    max_wait_seconds: float = 5.0,
) -> AsyncRetrying:
    """
    Build a tenacity AsyncRetrying for HTTP calls.

    Usage:
        async for attempt in build_retry_policy():
            with attempt:
                response = await client.get(...)
    """
    return AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=min_wait_seconds, max=max_wait_seconds),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
        reraise=True,
    )


# -----------------------------------------------------------------------------
# Timing
# -----------------------------------------------------------------------------


@asynccontextmanager
async def measure_duration():  # noqa: ANN201 — yields a callable
    """
    Async context manager that measures elapsed milliseconds.

    Usage:
        async with measure_duration() as elapsed:
            await do_something()
        duration_ms = elapsed()
    """
    start = time.perf_counter()

    def elapsed() -> int:
        return int((time.perf_counter() - start) * 1000)

    yield elapsed


async def run_with_retry(
    operation: Callable[[], Coroutine[Any, Any, T]],
    *,
    max_attempts: int = 3,
    service_name: str = "external",
) -> T:
    """
    Execute an async operation with retry-on-transient-failure.

    Logs each failed attempt but only raises if all attempts fail.
    """
    async for attempt in build_retry_policy(max_attempts=max_attempts):
        with attempt:
            try:
                return await operation()
            except RETRYABLE_EXCEPTIONS as e:
                logger.warning(
                    "http_retry",
                    service=service_name,
                    attempt=attempt.retry_state.attempt_number,
                    error=str(e),
                )
                raise
    # Unreachable if reraise=True, but satisfies mypy
    raise RuntimeError("retry loop exited unexpectedly")
