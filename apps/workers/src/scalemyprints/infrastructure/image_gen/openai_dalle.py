"""
OpenAI DALL-E 3 adapter.

DALL-E 3 supports three sizes:
  - 1024x1024 (square)
  - 1024x1792 (portrait)
  - 1792x1024 (landscape)

Quality: "standard" or "hd" — we always use "hd" for POD output.
Each call returns a single image — for variant_count > 1 we issue
parallel requests with different seeds.

Pricing (Jan 2025): hd 1024x1024 = $0.080, hd 1024x1792 = $0.120.
"""

from __future__ import annotations

import asyncio
import base64
import time

import httpx

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)
from scalemyprints.domain.design.models import ProvenanceRecord
from scalemyprints.domain.design.ports import GeneratedImage, ImageGenResult
from scalemyprints.domain.design.style_presets import ASPECT_SPECS
from scalemyprints.infrastructure.trademark_apis.base import HttpClientFactory

logger = get_logger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com"
DALLE_MODEL = "dall-e-3"


# DALL-E 3 only accepts these three sizes.
def _dalle_size(aspect: DesignAspect) -> str:
    spec = ASPECT_SPECS[aspect]
    if spec.width == spec.height:
        return "1024x1024"
    if spec.width > spec.height:
        return "1792x1024"
    return "1024x1792"


COST_PER_IMAGE_USD: dict[str, float] = {
    "1024x1024": 0.080,  # hd
    "1024x1792": 0.120,  # hd
    "1792x1024": 0.120,  # hd
}


class OpenAIDalleAdapter:
    """OpenAI DALL-E 3 adapter."""

    def __init__(
        self,
        *,
        api_key: str,
        http_factory: HttpClientFactory | None = None,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout_seconds: float = 90.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = request_timeout_seconds
        self._factory = http_factory or HttpClientFactory(
            timeout_seconds=request_timeout_seconds,
        )
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> ImageGenProviderName:
        return ImageGenProviderName.OPENAI_DALLE3

    def _client_or_build(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._factory.build(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def generate(
        self,
        *,
        enriched_prompt: str,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        variant_count: int,
        negative_prompt: str | None = None,
        seed: int | None = None,
    ) -> ImageGenResult:
        start = time.monotonic()
        size = _dalle_size(aspect)
        spec = ASPECT_SPECS[aspect]

        # DALL-E 3 only returns one image per call. For variants we fan out.
        coros = [
            self._single_call(
                enriched_prompt=enriched_prompt,
                raw_prompt=raw_prompt,
                style=style,
                aspect=aspect,
                output_format=output_format,
                size=size,
                spec_width=spec.width,
                spec_height=spec.height,
                seed=seed,
            )
            for _ in range(variant_count)
        ]
        results = await asyncio.gather(*coros, return_exceptions=False)

        successes: list[GeneratedImage] = []
        last_error: str | None = None
        last_reason: FailureReason | None = None
        for r in results:
            img, err, reason = r
            if img is not None:
                successes.append(img)
            else:
                last_error = err
                last_reason = reason

        duration_ms = int((time.monotonic() - start) * 1000)
        if not successes:
            return ImageGenResult(
                images=[],
                provider=self.provider_name,
                duration_ms=duration_ms,
                error=last_error or "dalle_unknown_error",
                failure_reason=last_reason or FailureReason.PROVIDER_UNAVAILABLE,
            )
        return ImageGenResult(
            images=successes,
            provider=self.provider_name,
            duration_ms=duration_ms,
            error=None,
        )

    async def _single_call(  # noqa: PLR0911
        self,
        *,
        enriched_prompt: str,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        size: str,
        spec_width: int,
        spec_height: int,
        seed: int | None,
    ) -> tuple[GeneratedImage | None, str | None, FailureReason | None]:
        client = self._client_or_build()
        body = {
            "model": DALLE_MODEL,
            "prompt": enriched_prompt[:4000],  # DALL-E hard limit
            "n": 1,
            "size": size,
            "quality": "hd",
            "response_format": "b64_json",
        }
        try:
            response = await client.post(
                "/v1/images/generations",
                json=body,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return None, "provider_timeout", FailureReason.PROVIDER_UNAVAILABLE
        except httpx.HTTPError as e:
            return None, f"http_error:{type(e).__name__}", FailureReason.PROVIDER_UNAVAILABLE

        if response.status_code == 401:
            return None, "invalid_api_key", FailureReason.PROVIDER_UNAVAILABLE
        if response.status_code == 429:
            return None, "rate_limited", FailureReason.PROVIDER_RATE_LIMITED
        if response.status_code == 400:
            try:
                err_body = response.json()
            except ValueError:
                err_body = {}
            err_code = (err_body.get("error") or {}).get("code") or ""
            if "content_policy" in err_code or "moderation" in err_code:
                return None, "content_policy", FailureReason.POLICY_VIOLATION
            return None, f"bad_request:{err_code or 'unknown'}", FailureReason.INVALID_PROMPT
        if response.status_code >= 400:
            return None, f"http_{response.status_code}", FailureReason.PROVIDER_UNAVAILABLE

        try:
            data = response.json()
        except ValueError:
            return None, "invalid_json_response", FailureReason.PROVIDER_UNAVAILABLE

        items = data.get("data") or []
        if not items:
            return None, "no_images_in_response", FailureReason.PROVIDER_UNAVAILABLE

        b64 = items[0].get("b64_json")
        revised_prompt = items[0].get("revised_prompt") or enriched_prompt
        if not b64:
            return None, "missing_b64_payload", FailureReason.PROVIDER_UNAVAILABLE

        try:
            image_bytes = base64.b64decode(b64)
        except (ValueError, TypeError):
            return None, "invalid_base64", FailureReason.PROVIDER_UNAVAILABLE

        # DALL-E always returns the size we requested.
        actual_w, actual_h = (int(x) for x in size.split("x"))

        cost = COST_PER_IMAGE_USD.get(size)
        provenance = ProvenanceRecord(
            provider=self.provider_name,
            model=DALLE_MODEL,
            seed=seed,
            enriched_prompt=revised_prompt,
            raw_prompt=raw_prompt,
            style=style,
            aspect=aspect,
            cost_usd=cost,
            duration_ms=0,  # filled by caller's outer timer
        )
        return (
            GeneratedImage(
                image_bytes=image_bytes,
                width=actual_w,
                height=actual_h,
                format=output_format,
                provenance=provenance,
            ),
            None,
            None,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
