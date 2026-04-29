"""
JWKS client — fetches Supabase's public keys for JWT verification.

Modern Supabase signs JWTs with asymmetric keys (RS256 or ES256). The
public keys are exposed at /auth/v1/.well-known/jwks.json. We fetch them
once, cache them in memory, and refresh periodically.

This replaces the old "shared HS256 secret" model entirely. No secret
needs to be configured anywhere — the public keys are, well, public.

Cache strategy:
- Fetch on first request
- Cache for `cache_ttl_seconds` (default 1 hour)
- On verification failure (e.g., key rotation), force a fresh fetch
- Concurrent fetches deduplicated via asyncio.Lock
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx
from jwt import PyJWK, PyJWKSet

from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class _CachedJWKS:
    """JWKS plus the time it was fetched."""

    keys: PyJWKSet
    fetched_at: float


class JWKSClient:
    """
    Fetches and caches a JSON Web Key Set from a remote URL.

    Designed for use as a process-wide singleton (one per JWKS endpoint).
    Thread-safe via asyncio.Lock.
    """

    def __init__(
        self,
        jwks_url: str,
        *,
        cache_ttl_seconds: int = 3600,  # 1 hour default
        request_timeout_seconds: float = 5.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._cache_ttl = cache_ttl_seconds
        self._timeout = request_timeout_seconds
        self._http = http_client
        self._owns_http = http_client is None
        self._cached: _CachedJWKS | None = None
        self._lock = asyncio.Lock()

    async def get_signing_key(self, kid: str) -> PyJWK:
        """
        Return the signing key for a given `kid` (key ID from JWT header).

        On miss, refreshes the JWKS once before raising. This handles the
        common case where Supabase rotates keys mid-session.
        """
        # Fast path: cached and not expired
        cached = await self._get_cached()
        try:
            return cached.from_jwk(kid)
        except (KeyError, AttributeError):
            pass  # try fresh fetch

        # Cache miss / unknown key — force refresh once
        logger.info("jwks_force_refresh", kid=kid, url=self._jwks_url)
        fresh = await self._refresh()
        try:
            return fresh.from_jwk(kid)
        except (KeyError, AttributeError) as e:
            raise KeyError(f"No signing key found for kid={kid}") from e

    async def _get_cached(self) -> PyJWKSet:
        """Return the current cached JWKS, refreshing if expired."""
        async with self._lock:
            now = time.monotonic()
            if (
                self._cached is None
                or (now - self._cached.fetched_at) >= self._cache_ttl
            ):
                await self._refresh_unsafe()
            assert self._cached is not None
            return self._cached.keys

    async def _refresh(self) -> PyJWKSet:
        """Force-refresh the JWKS regardless of cache age."""
        async with self._lock:
            await self._refresh_unsafe()
            assert self._cached is not None
            return self._cached.keys

    async def _refresh_unsafe(self) -> None:
        """Fetch JWKS from network. Caller must hold self._lock."""
        client = self._http or httpx.AsyncClient(timeout=self._timeout)
        try:
            response = await client.get(self._jwks_url, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            self._cached = _CachedJWKS(
                keys=PyJWKSet.from_dict(payload),
                fetched_at=time.monotonic(),
            )
            logger.info(
                "jwks_refreshed",
                url=self._jwks_url,
                key_count=len(payload.get("keys", [])),
            )
        finally:
            if self._owns_http:
                await client.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client if we own it."""
        if self._http and self._owns_http:
            await self._http.aclose()
