"""MemoryDesignStorage — round-trip data URL output."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import OutputFormat
from scalemyprints.infrastructure.storage.memory_storage import MemoryDesignStorage


@pytest.mark.unit
class TestMemoryDesignStorage:
    async def test_store_returns_data_url(self) -> None:
        storage = MemoryDesignStorage()
        artifact = await storage.store(
            user_id="u1",
            job_id="j1",
            artifact_index=0,
            image_bytes=b"\x89PNG\r\nfake",
            format=OutputFormat.PNG_TRANSPARENT,
        )

        assert artifact.error is None
        assert artifact.storage_path == "u1/j1/0.png"
        assert artifact.public_url is not None
        assert artifact.public_url.startswith("data:image/png;base64,")
        assert artifact.bytes_size == len(b"\x89PNG\r\nfake")

    async def test_signed_url_returns_same_data_url(self) -> None:
        storage = MemoryDesignStorage()
        await storage.store(
            user_id="u1",
            job_id="j1",
            artifact_index=0,
            image_bytes=b"data",
            format=OutputFormat.PNG,
        )
        url = await storage.signed_url("u1/j1/0.png")
        assert url is not None
        assert url.startswith("data:image/png;base64,")

    async def test_signed_url_returns_none_for_unknown_path(self) -> None:
        storage = MemoryDesignStorage()
        url = await storage.signed_url("nope/nope/nope.png")
        assert url is None
