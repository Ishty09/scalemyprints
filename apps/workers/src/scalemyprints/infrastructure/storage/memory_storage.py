"""
In-memory design storage — used for local dev (when Supabase not configured)
and unit tests. NOT for production.

Stores image bytes in a dict keyed by storage_path. Exposes them through
data-URLs so the web UI can still preview locally.
"""

from __future__ import annotations

import base64

from scalemyprints.domain.design.enums import OutputFormat
from scalemyprints.domain.design.ports import StoredArtifact

_FORMAT_EXT: dict[OutputFormat, tuple[str, str]] = {
    OutputFormat.PNG: ("png", "image/png"),
    OutputFormat.PNG_TRANSPARENT: ("png", "image/png"),
    OutputFormat.WEBP: ("webp", "image/webp"),
}


class MemoryDesignStorage:
    """Process-local design storage (dev/test only)."""

    def __init__(self) -> None:
        self._blobs: dict[str, tuple[bytes, str]] = {}

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
        self._blobs[key] = (image_bytes, content_type)
        url = self._data_url(image_bytes, content_type)
        return StoredArtifact(
            storage_path=key,
            public_url=url,
            thumbnail_url=url,
            bytes_size=len(image_bytes),
            error=None,
        )

    async def signed_url(
        self,
        storage_path: str,
        ttl_seconds: int = 60 * 60 * 24,
    ) -> str | None:
        entry = self._blobs.get(storage_path)
        if not entry:
            return None
        return self._data_url(*entry)

    @staticmethod
    def _data_url(image_bytes: bytes, content_type: str) -> str:
        b64 = base64.b64encode(image_bytes).decode("ascii")
        return f"data:{content_type};base64,{b64}"
