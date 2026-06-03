"""Tests for the API-key bearer auth dependency and the in-memory key store."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from scalemyprints.api.middleware.api_key_auth import (
    _extract_bearer,
    get_api_key_user,
)
from scalemyprints.infrastructure.spy_storage.memory_watchlist_store import (
    MemoryApiKeyStore,
    generate_api_key,
)


class _StubContainer:
    def __init__(self, store: MemoryApiKeyStore) -> None:
        self.spy_api_key_store = store


def test_extract_bearer_happy_path() -> None:
    assert _extract_bearer("Bearer smp_xyz") == "smp_xyz"
    assert _extract_bearer("bearer smp_abc") == "smp_abc"


def test_extract_bearer_rejects_non_smp_token() -> None:
    assert _extract_bearer("Bearer not_an_smp_token") is None


def test_extract_bearer_rejects_wrong_scheme() -> None:
    assert _extract_bearer("Token smp_abc") is None


def test_extract_bearer_handles_empty() -> None:
    assert _extract_bearer(None) is None
    assert _extract_bearer("") is None
    assert _extract_bearer("Bearer") is None


def test_generate_api_key_format() -> None:
    raw, prefix, hashed = generate_api_key()
    assert raw.startswith("smp_")
    assert raw[:10] == prefix
    assert len(hashed) == 64  # sha256 hex
    assert hashed != raw


@pytest.mark.asyncio
async def test_resolve_round_trip() -> None:
    store = MemoryApiKeyStore()
    key, raw = await store.create(user_id="u1", label="prod")
    found = await store.resolve(raw)
    assert found is not None
    assert found.id == key.id
    assert found.user_id == "u1"


@pytest.mark.asyncio
async def test_resolve_returns_none_for_unknown_key() -> None:
    store = MemoryApiKeyStore()
    found = await store.resolve("smp_does_not_exist_at_all")
    assert found is None


@pytest.mark.asyncio
async def test_revoked_key_does_not_resolve() -> None:
    store = MemoryApiKeyStore()
    key, raw = await store.create(user_id="u1", label="prod")
    assert await store.revoke(key.id, "u1") is True
    assert await store.resolve(raw) is None


@pytest.mark.asyncio
async def test_get_api_key_user_resolves_known_key() -> None:
    store = MemoryApiKeyStore()
    _key, raw = await store.create(user_id="u-42", label="prod")
    container = _StubContainer(store)
    user = await get_api_key_user(
        authorization=f"Bearer {raw}",
        container=container,  # type: ignore[arg-type]
    )
    assert user.id == "u-42"
    assert user.is_anonymous is False


@pytest.mark.asyncio
async def test_get_api_key_user_rejects_missing_header() -> None:
    store = MemoryApiKeyStore()
    container = _StubContainer(store)
    with pytest.raises(HTTPException) as excinfo:
        await get_api_key_user(authorization=None, container=container)  # type: ignore[arg-type]
    assert excinfo.value.status_code == 401


@pytest.mark.asyncio
async def test_get_api_key_user_rejects_revoked_key() -> None:
    store = MemoryApiKeyStore()
    key, raw = await store.create(user_id="u1", label="prod")
    await store.revoke(key.id, "u1")
    container = _StubContainer(store)
    with pytest.raises(HTTPException) as excinfo:
        await get_api_key_user(
            authorization=f"Bearer {raw}",
            container=container,  # type: ignore[arg-type]
        )
    assert excinfo.value.status_code == 401
