"""
Supabase Storage adapter for design artifacts.

Layout: bucket "designs", key pattern "{user_id}/{job_id}/{index}.{ext}".

We upload via the supabase-py client. Upload calls are sync under the
hood; we run them in a thread to keep the orchestrator async.

Returned URL is a long-lived signed URL (24h default) — the bucket is
configured private so anonymous access is denied.
"""

from __future__ import annotations

import asyncio
import contextlib
from functools import partial

from supabase import Client, create_client

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import OutputFormat
from scalemyprints.domain.design.ports import StoredArtifact

logger = get_logger(__name__)


_FORMAT_EXT: dict[OutputFormat, tuple[str, str]] = {
    OutputFormat.PNG: ("png", "image/png"),
    OutputFormat.PNG_TRANSPARENT: ("png", "image/png"),
    OutputFormat.WEBP: ("webp", "image/webp"),
}


class SupabaseDesignStorage:
    """Persists design artifacts to a Supabase Storage bucket."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        bucket: str = "designs",
        signed_url_ttl_seconds: int = 60 * 60 * 24,
    ) -> None:
        if not supabase_url or not service_role_key:
            raise ValueError("supabase_url + service_role_key required")
        self._client: Client = create_client(supabase_url, service_role_key)
        self._bucket = bucket
        self._ttl = signed_url_ttl_seconds

    async def store(
        self,
        *,
        user_id: str,
        job_id: str,
        artifact_index: int,
        image_bytes: bytes,
        format: OutputFormat,
    ) -> StoredArtifact:
        ext, content_type = _FORMAT_EXT[format]
        key = f"{user_id}/{job_id}/{artifact_index}.{ext}"

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                partial(
                    self._client.storage.from_(self._bucket).upload,
                    key,
                    image_bytes,
                    {
                        "content-type": content_type,
                        "cache-control": "public, max-age=31536000, immutable",
                        "upsert": "true",
                    },
                ),
            )
        except Exception as e:
            logger.warning("design_storage_upload_failed", key=key, error=str(e)[:200])
            return StoredArtifact(
                storage_path=key,
                bytes_size=len(image_bytes),
                error=f"upload_failed:{type(e).__name__}",
            )

        url = await self.signed_url(key, ttl_seconds=self._ttl)
        return StoredArtifact(
            storage_path=key,
            public_url=url,
            thumbnail_url=url,  # one-and-the-same until we add real thumbnailing
            bytes_size=len(image_bytes),
            error=None,
        )

    async def signed_url(
        self,
        storage_path: str,
        ttl_seconds: int = 60 * 60 * 24,
    ) -> str | None:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(
                    self._client.storage.from_(self._bucket).create_signed_url,
                    storage_path,
                    ttl_seconds,
                ),
            )
        except Exception as e:
            logger.warning(
                "design_storage_signed_url_failed",
                key=storage_path,
                error=str(e)[:200],
            )
            return None
        if isinstance(result, dict):
            url = result.get("signedURL") or result.get("signed_url")
            return url if isinstance(url, str) else None
        return None

    async def aclose(self) -> None:
        # supabase-py has no explicit close; underlying httpx is GC'd.
        with contextlib.suppress(Exception):
            self._client = None  # type: ignore[assignment]
