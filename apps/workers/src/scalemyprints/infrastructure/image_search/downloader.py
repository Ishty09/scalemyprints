"""
Image downloader — fetches raw image bytes from a public URL.

Uses curl_cffi when available (TLS fingerprint spoofing — helps on
hosts that block typical Python/httpx user agents). Falls back to
httpx otherwise. Caps response size at 20 MB.
"""

from __future__ import annotations

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.ports import ImageDownloader, ImageDownloadResult

logger = get_logger(__name__)

MAX_BYTES = 20 * 1024 * 1024  # 20 MB cap


class HttpxImageDownloader(ImageDownloader):
    """Vanilla httpx-based downloader."""

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self._timeout = timeout_seconds

    async def download(self, url: str) -> ImageDownloadResult:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=self._timeout, follow_redirects=True) as c:
                resp = await c.get(url, headers={"User-Agent": "ScaleMyPrintsSpy/1.0"})
                resp.raise_for_status()
                if len(resp.content) > MAX_BYTES:
                    return ImageDownloadResult(
                        image_bytes=b"",
                        content_type="",
                        bytes_size=1,
                        source_url=url,  # type: ignore[arg-type]
                        error=f"image_too_large: {len(resp.content)}",
                    )
                return ImageDownloadResult(
                    image_bytes=resp.content,
                    content_type=resp.headers.get("content-type", "image/png"),
                    bytes_size=len(resp.content),
                    source_url=url,  # type: ignore[arg-type]
                )
        except Exception as e:
            logger.warning("image_download_failed", url=url, error=str(e))
            return ImageDownloadResult(
                image_bytes=b"",
                content_type="",
                bytes_size=1,
                source_url=url,  # type: ignore[arg-type]
                error=f"download_failed: {e}",
            )


class CurlCffiImageDownloader(ImageDownloader):
    """
    curl_cffi-based downloader with browser TLS fingerprint impersonation.

    Useful for hosts (Etsy/Redbubble) that fingerprint vanilla httpx
    and refuse the request. Falls back to httpx if curl_cffi missing.
    """

    def __init__(self, *, timeout_seconds: float = 10.0, impersonate: str = "chrome124") -> None:
        self._timeout = timeout_seconds
        self._impersonate = impersonate
        self._fallback = HttpxImageDownloader(timeout_seconds=timeout_seconds)

    async def download(self, url: str) -> ImageDownloadResult:
        try:
            from curl_cffi.requests import AsyncSession  # heavy
        except ImportError:
            return await self._fallback.download(url)

        try:
            async with AsyncSession(impersonate=self._impersonate, timeout=self._timeout) as s:
                resp = await s.get(url, allow_redirects=True)
                if resp.status_code >= 400:
                    return ImageDownloadResult(
                        image_bytes=b"",
                        content_type="",
                        bytes_size=1,
                        source_url=url,  # type: ignore[arg-type]
                        error=f"http_{resp.status_code}",
                    )
                content = resp.content
                if len(content) > MAX_BYTES:
                    return ImageDownloadResult(
                        image_bytes=b"",
                        content_type="",
                        bytes_size=1,
                        source_url=url,  # type: ignore[arg-type]
                        error=f"image_too_large: {len(content)}",
                    )
                return ImageDownloadResult(
                    image_bytes=content,
                    content_type=resp.headers.get("content-type", "image/png"),
                    bytes_size=len(content),
                    source_url=url,  # type: ignore[arg-type]
                )
        except Exception as e:
            logger.warning("curl_cffi_download_failed_falling_back", url=url, error=str(e))
            return await self._fallback.download(url)
