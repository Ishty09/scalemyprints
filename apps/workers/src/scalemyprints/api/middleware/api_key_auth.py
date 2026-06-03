"""
API key bearer auth for the Spy public router.

Accepts:
  Authorization: Bearer smp_<token>

Resolves the key via the configured ApiKeyStore (memory in dev,
Supabase in prod). On success, returns a `CurrentUser` populated
from the key's user_id.

Anonymous fallback is NOT supported here — every /spy/public/*
endpoint requires a valid key. Use the JWT-authed endpoints for
the dashboard.
"""

from __future__ import annotations

from typing import Annotated, Protocol, runtime_checkable

from fastapi import Depends, Header, HTTPException, status

from scalemyprints.api.deps import get_service_container
from scalemyprints.api.middleware.auth import CurrentUser
from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.watchlist_models import SpyApiKey
from scalemyprints.infrastructure.container import ServiceContainer  # noqa: TC001

logger = get_logger(__name__)


@runtime_checkable
class ApiKeyResolver(Protocol):
    async def resolve(self, raw_key: str) -> SpyApiKey | None: ...


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2:
        return None
    scheme, token = parts
    if scheme.lower() != "bearer":
        return None
    token = token.strip()
    if not token.startswith("smp_"):
        return None
    return token


async def get_api_key_user(
    authorization: Annotated[str | None, Header()] = None,
    container: Annotated[ServiceContainer, Depends(get_service_container)] = None,  # type: ignore[assignment]
) -> CurrentUser:
    raw = _extract_bearer(authorization)
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "missing_api_key",
                "message": "Bearer smp_... API key required",
            },
        )
    store: ApiKeyResolver = container.spy_api_key_store
    key = await store.resolve(raw)
    if key is None or key.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_api_key", "message": "Unknown or revoked key"},
        )

    logger.info(
        "api_key_authenticated",
        key_id=key.id,
        user_id=key.user_id,
        scopes=key.scopes,
    )
    return CurrentUser(id=key.user_id, email=None, is_anonymous=False)
