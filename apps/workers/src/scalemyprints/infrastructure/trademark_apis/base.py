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
import urllib.parse
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


class _RelayTransport(httpx.AsyncBaseTransport):
    """
    Routes all HTTP requests through a Cloudflare Worker relay endpoint.

    The relay (apps/web/api/uk-trademark-relay) re-issues the fetch() from
    Cloudflare's IP space, bypassing datacenter IP blocks on UKIPO/TMview.

    The relay URL receives:  GET {relay}?url={encoded_target_url}
    Header:                  x-relay-secret: {secret}
    """

    def __init__(self, relay_url: str, relay_secret: str) -> None:
        self._relay_url = relay_url.rstrip("/")
        self._relay_secret = relay_secret
        self._inner = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        target = str(request.url)
        relay_request = httpx.Request(
            "GET",
            f"{self._relay_url}?url={urllib.parse.quote(target, safe='')}",
            headers={"x-relay-secret": self._relay_secret},
        )
        return await self._inner.handle_async_request(relay_request)

    async def aclose(self) -> None:
        await self._inner.aclose()


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
        proxy_url: str | None = None,
        relay_url: str | None = None,
        relay_secret: str = "",
    ) -> None:
        self._user_agent = user_agent
        self._timeout = httpx.Timeout(
            timeout=timeout_seconds,
            connect=connect_timeout_seconds,
        )
        self._timeout_seconds = timeout_seconds
        self._proxy_url = proxy_url
        self._relay_url = relay_url
        self._relay_secret = relay_secret

    def build(self, base_url: str, headers: dict[str, str] | None = None) -> httpx.AsyncClient:
        """Construct a new client bound to the given base URL."""
        final_headers = {
            "User-Agent": self._user_agent,
            "Accept": "application/json, text/plain, */*",
        }
        if headers:
            final_headers.update(headers)

        # relay_url takes priority over proxy_url (can't use both simultaneously)
        transport: httpx.AsyncBaseTransport | None = None
        proxy: str | None = self._proxy_url
        if self._relay_url:
            transport = _RelayTransport(self._relay_url, self._relay_secret)
            proxy = None

        return httpx.AsyncClient(
            base_url=base_url,
            headers=final_headers,
            proxy=proxy,
            transport=transport,
            timeout=self._timeout,
            follow_redirects=True,
            # Conservative pool: trademark APIs have rate limits
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )

    def build_browser(
        self,
        base_url: str,
        headers: dict[str, str] | None = None,
        *,
        impersonate: str = "chrome124",
    ) -> "BrowserAsyncClient":
        """
        Build a TLS-fingerprint-spoofing client (curl_cffi-based).

        Mimics a real Chrome/Edge/Safari TLS handshake — bypasses anti-bot
        systems that rely on JA3 fingerprinting (Akamai, DataDome, PerimeterX,
        Cloudflare bot management). Use this for endpoints that block
        datacenter IPs purely on TLS fingerprint:

        - tmdn.org (TMView Akamai challenge)
        - www.etsy.com (Etsy 403/429)

        Note: this does NOT change the egress IP — if the block is purely
        IP-based (e.g., Cloudflare WAF on UKIPO), use a residential proxy.
        """
        return BrowserAsyncClient(
            base_url=base_url,
            headers={
                "User-Agent": self._user_agent,
                "Accept": "application/json, text/plain, */*",
                **(headers or {}),
            },
            timeout_seconds=self._timeout_seconds,
            impersonate=impersonate,
            proxy_url=self._proxy_url,
        )


# -----------------------------------------------------------------------------
# Browser-impersonating async client (curl_cffi wrapper)
# -----------------------------------------------------------------------------


class BrowserAsyncClient:
    """
    httpx.AsyncClient-compatible client backed by curl_cffi.

    Sends TLS handshakes indistinguishable from a real Chrome browser.
    Drop-in replacement for httpx.AsyncClient where adapters use
    `.get(path, params=...)`, `.post(path, json=...)`, `response.text`,
    `response.json()`, `response.status_code`, `response.raise_for_status()`,
    and `.aclose()`.
    """

    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        impersonate: str = "chrome124",
        proxy_url: str | None = None,
    ) -> None:
        # Imported lazily so tests/imports don't require the binary wheels.
        from curl_cffi.requests import AsyncSession

        self._base_url = base_url.rstrip("/")
        self._default_headers = dict(headers or {})
        self._timeout = timeout_seconds
        self._session = AsyncSession(
            impersonate=impersonate,
            timeout=timeout_seconds,
            proxies={"http": proxy_url, "https": proxy_url} if proxy_url else None,
        )

    def _full_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not self._base_url:
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    async def get(
        self,
        path: str,
        *,
        params: Any = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> Any:
        merged = {**self._default_headers, **(headers or {})}
        return await self._session.get(
            self._full_url(path),
            params=params,
            headers=merged,
            timeout=timeout if timeout is not None else self._timeout,
        )

    async def post(
        self,
        path: str,
        *,
        params: Any = None,
        headers: dict[str, str] | None = None,
        json: Any = None,
        data: Any = None,
        timeout: float | None = None,
    ) -> Any:
        merged = {**self._default_headers, **(headers or {})}
        return await self._session.post(
            self._full_url(path),
            params=params,
            headers=merged,
            json=json,
            data=data,
            timeout=timeout if timeout is not None else self._timeout,
        )

    async def aclose(self) -> None:
        await self._session.close()


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
