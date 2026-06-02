"""
Disabled image-gen provider.

Used when IMAGE_GEN_PROVIDER=disabled or no provider credentials are
configured. Returns a structured error so the orchestrator can mark
the job FAILED with a sensible reason instead of crashing.
"""

from __future__ import annotations

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)
from scalemyprints.domain.design.ports import ImageGenResult


class DisabledImageGenProvider:
    """No-op adapter — always errors with provider_unavailable."""

    @property
    def provider_name(self) -> ImageGenProviderName:
        return ImageGenProviderName.DISABLED

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
        return ImageGenResult(
            images=[],
            provider=ImageGenProviderName.DISABLED,
            duration_ms=0,
            error="image_gen_disabled",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
