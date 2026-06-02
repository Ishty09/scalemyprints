"""
Supabase pgvector-backed EmbeddingStore.

Schema (created by 20260603000000_spy_phase_1.sql):

  spy_design_embeddings:
    sha256          text PK
    phash           bigint
    clip_embedding  vector(512)
    width / height / bytes_size
    created_at

  spy_design_listing_links:
    sha256          text → spy_design_embeddings(sha256)
    listing_id      uuid → spy_listings(id)
    PRIMARY KEY (sha256, listing_id)

Search RPCs (defined in the migration):
  spy_search_phash(target_hash bigint, max_distance int, lim int)
  spy_search_clip(query vector, min_cosine float, lim int)

These RPCs return JSON arrays of {sha256, listing_ids, distance, cosine}.
We talk to Supabase via REST (PostgREST) using the service role key —
the same pattern the SupabaseDesignJobStore uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ports import EmbeddingSearchHit, EmbeddingStore

if TYPE_CHECKING:
    from scalemyprints.domain.spy.models import DesignEmbedding

logger = get_logger(__name__)


class SupabasePgvectorStore(EmbeddingStore):
    """REST-based pgvector store backed by Supabase RPCs."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        timeout_seconds: float = 8.0,
    ) -> None:
        self._url = supabase_url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        }
        self._timeout = timeout_seconds
        self._client: httpx.AsyncClient | None = None

    # ----- Lifecycle ------------------------------------------------------

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ----- Mutations ------------------------------------------------------

    async def upsert(self, embedding: DesignEmbedding) -> None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_design_embeddings"
        params = {"on_conflict": "sha256"}
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates"}
        payload = {
            "sha256": embedding.sha256,
            "phash": embedding.phash,
            "clip_embedding": embedding.clip_embedding,
            "width": embedding.width,
            "height": embedding.height,
            "bytes_size": embedding.bytes_size,
            "source_url": str(embedding.source_url) if embedding.source_url else None,
            "created_at": embedding.created_at.isoformat(),
        }
        resp = await client.post(url, params=params, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning(
                "pgvector_upsert_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )
            resp.raise_for_status()

    async def link_listing(self, sha256: str, listing_id: str) -> None:
        client = await self._http()
        url = f"{self._url}/rest/v1/spy_design_listing_links"
        headers = {**self._headers, "Prefer": "resolution=merge-duplicates"}
        payload = {"sha256": sha256, "listing_id": listing_id}
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400 and resp.status_code != 409:  # 409 = already linked
            logger.warning(
                "pgvector_link_failed",
                status=resp.status_code,
                body=resp.text[:300],
            )

    # ----- Search ---------------------------------------------------------

    async def search_phash(
        self,
        phash: int,
        *,
        max_distance: int = 12,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]:
        client = await self._http()
        url = f"{self._url}/rest/v1/rpc/spy_search_phash"
        payload = {
            "target_hash": phash,
            "max_distance": max_distance,
            "lim": limit,
        }
        try:
            resp = await client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            logger.warning("pgvector_phash_search_failed", error=str(e))
            return []

        return [
            EmbeddingSearchHit(
                sha256=row["sha256"],
                listing_ids=row.get("listing_ids") or [],
                phash_distance=row.get("distance"),
            )
            for row in rows
        ]

    async def search_clip(
        self,
        vector: list[float],
        *,
        min_cosine: float = 0.70,
        limit: int = 50,
    ) -> list[EmbeddingSearchHit]:
        client = await self._http()
        url = f"{self._url}/rest/v1/rpc/spy_search_clip"
        payload = {
            "query": vector,
            "min_cosine": min_cosine,
            "lim": limit,
        }
        try:
            resp = await client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            rows = resp.json()
        except Exception as e:
            logger.warning("pgvector_clip_search_failed", error=str(e))
            return []

        return [
            EmbeddingSearchHit(
                sha256=row["sha256"],
                listing_ids=row.get("listing_ids") or [],
                clip_cosine=row.get("cosine"),
            )
            for row in rows
        ]
