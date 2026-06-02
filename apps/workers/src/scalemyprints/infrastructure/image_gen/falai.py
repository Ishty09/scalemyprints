"""
Fal.ai Flux adapter.

Fal serves Flux Schnell (fast, free tier) and Flux Pro (higher quality,
paid). Both use the same endpoint shape:

    POST https://fal.run/fal-ai/flux/schnell
    Authorization: Key <FAL_KEY>
    Content-Type: application/json
    body: {
      "prompt": "...",
      "image_size": {"width": 1024, "height": 1024},
      "num_images": 1,
      "num_inference_steps": 4,    # Schnell: 1-4
      "seed": 12345                  # optional
    }
    response: {
      "images": [{"url": "https://...", "width": ..., "height": ..., "content_type": "image/png"}],
      "seed": 12345
    }

We download each image's bytes inline so the storage adapter only
sees in-memory blobs (no signed-URL leakage to Supabase).

Adapter never raises — wraps everything in try/except and returns
ImageGenResult with `error` set on failure.
"""

from __future__ import annotations

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


# Fal model slugs — keep in one place so we can swap quality tiers.
FAL_MODELS: dict[ImageGenProviderName, str] = {
    ImageGenProviderName.FAL_FLUX_SCHNELL: "fal-ai/flux/schnell",
    ImageGenProviderName.FAL_FLUX_PRO: "fal-ai/flux-pro",
}

# Cost per image (informational — Fal updates pricing; verify quarterly).
FAL_COST_PER_IMAGE_USD: dict[ImageGenProviderName, float] = {
    ImageGenProviderName.FAL_FLUX_SCHNELL: 0.003,
    ImageGenProviderName.FAL_FLUX_PRO: 0.05,
}

DEFAULT_BASE_URL = "https://fal.run"


class FalFluxAdapter:
    """Fal.ai Flux adapter (Schnell or Pro)."""

    def __init__(
        self,
        *,
        api_key: str,
        provider: ImageGenProviderName = ImageGenProviderName.FAL_FLUX_SCHNELL,
        http_factory: HttpClientFactory | None = None,
        base_url: str = DEFAULT_BASE_URL,
        request_timeout_seconds: float = 60.0,
    ) -> None:
        if provider not in FAL_MODELS:
            raise ValueError(f"Unsupported Fal provider: {provider}")
        self._api_key = api_key
        self._provider = provider
        self._model_slug = FAL_MODELS[provider]
        self._base_url = base_url.rstrip("/")
        self._timeout = request_timeout_seconds
        self._factory = http_factory or HttpClientFactory(
            timeout_seconds=request_timeout_seconds,
        )
        self._client: httpx.AsyncClient | None = None

    @property
    def provider_name(self) -> ImageGenProviderName:
        return self._provider

    def _client_or_build(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = self._factory.build(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Key {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def generate(  # noqa: PLR0911, PLR0912
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
        spec = ASPECT_SPECS[aspect]
        client = self._client_or_build()

        payload: dict[str, object] = {
            "prompt": enriched_prompt,
            "image_size": {"width": spec.width, "height": spec.height},
            "num_images": variant_count,
            "enable_safety_checker": True,
        }
        if seed is not None:
            payload["seed"] = seed
        if self._provider == ImageGenProviderName.FAL_FLUX_SCHNELL:
            payload["num_inference_steps"] = 4

        try:
            response = await client.post(
                f"/{self._model_slug}",
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="provider_timeout",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )
        except httpx.HTTPError as e:
            logger.warning("falai_http_error", error=str(e))
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"http_error:{type(e).__name__}",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )

        if response.status_code == 401:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="invalid_api_key",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )
        if response.status_code == 429:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="rate_limited",
                failure_reason=FailureReason.PROVIDER_RATE_LIMITED,
            )
        if response.status_code == 422:
            # Fal flags content-policy violations with 422.
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="content_policy",
                failure_reason=FailureReason.POLICY_VIOLATION,
            )
        if response.status_code >= 400:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"http_{response.status_code}",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )

        try:
            data = response.json()
        except ValueError:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="invalid_json_response",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )

        images_payload = data.get("images") or []
        if not images_payload:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="no_images_in_response",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )

        result_seed = data.get("seed", seed)
        cost_each = FAL_COST_PER_IMAGE_USD.get(self._provider)

        # Fetch each image's bytes.
        results: list[GeneratedImage] = []
        for img in images_payload:
            url = img.get("url")
            if not url:
                continue
            try:
                blob = await client.get(url, timeout=self._timeout)
            except httpx.HTTPError:
                continue
            if blob.status_code != 200:
                continue

            results.append(
                GeneratedImage(
                    image_bytes=blob.content,
                    width=int(img.get("width") or spec.width),
                    height=int(img.get("height") or spec.height),
                    format=output_format,
                    provenance=ProvenanceRecord(
                        provider=self._provider,
                        model=self._model_slug,
                        seed=result_seed if isinstance(result_seed, int) else None,
                        enriched_prompt=enriched_prompt,
                        raw_prompt=raw_prompt,
                        style=style,
                        aspect=aspect,
                        cost_usd=cost_each,
                        duration_ms=int((time.monotonic() - start) * 1000),
                    ),
                )
            )

        if not results:
            return ImageGenResult(
                images=[],
                provider=self._provider,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="failed_to_download_images",
                failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
            )

        duration_ms = int((time.monotonic() - start) * 1000)
        return ImageGenResult(
            images=results,
            provider=self._provider,
            duration_ms=duration_ms,
            error=None,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
