"""
Image-gen provider chain.

First-success-wins: walks the provider list in order, returning the
first ImageGenResult that has at least one image. Each provider is
wrapped in its own CircuitBreaker — repeatedly-failing providers are
skipped for the cooldown window so a single sick provider doesn't slow
every request.

Mirrors infrastructure/trademark_apis/provider_chain.py.
"""

from __future__ import annotations

import time

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)
from scalemyprints.domain.design.ports import ImageGenProvider, ImageGenResult
from scalemyprints.infrastructure.trademark_apis.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
)

logger = get_logger(__name__)


class ImageGenProviderChain:
    """First-success-wins chain across multiple image-gen providers."""

    def __init__(
        self,
        providers: list[tuple[str, ImageGenProvider]],
        breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        if not providers:
            raise ValueError("ImageGenProviderChain requires at least one provider")
        self._providers = providers
        self._breakers = {
            name: CircuitBreaker(name=f"design:{name}", config=breaker_config)
            for name, _ in providers
        }

    @property
    def provider_name(self) -> ImageGenProviderName:
        # Surface the first provider's name as the chain's default label.
        return self._providers[0][1].provider_name

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
        last_error: str | None = None
        last_reason: FailureReason | None = None
        last_provider: ImageGenProviderName | None = None

        for name, provider in self._providers:
            breaker = self._breakers[name]
            if not await breaker.allow():
                logger.info("design_provider_skipped_breaker_open", provider=name)
                continue

            try:
                result = await provider.generate(
                    enriched_prompt=enriched_prompt,
                    raw_prompt=raw_prompt,
                    style=style,
                    aspect=aspect,
                    output_format=output_format,
                    variant_count=variant_count,
                    negative_prompt=negative_prompt,
                    seed=seed,
                )
            except Exception as e:
                logger.warning(
                    "design_provider_raised_unexpectedly",
                    provider=name,
                    error=str(e),
                )
                await breaker.record_failure()
                last_error = f"adapter_raised:{type(e).__name__}"
                last_reason = FailureReason.PROVIDER_UNAVAILABLE
                last_provider = provider.provider_name
                continue

            last_provider = result.provider
            if result.images and not result.error:
                await breaker.record_success()
                logger.info(
                    "design_provider_success",
                    provider=name,
                    image_count=len(result.images),
                    duration_ms=result.duration_ms,
                )
                return result

            # Treat known terminal-policy/invalid-prompt failures as not-our-problem
            # — we should NOT fall through to the next provider for those, since
            # they will all reject the prompt the same way.
            if result.failure_reason in {
                FailureReason.POLICY_VIOLATION,
                FailureReason.INVALID_PROMPT,
            }:
                logger.info(
                    "design_provider_terminal_failure_no_fallback",
                    provider=name,
                    reason=result.failure_reason.value,
                )
                return result

            await breaker.record_failure()
            last_error = result.error
            last_reason = result.failure_reason
            logger.info(
                "design_provider_failed_falling_through",
                provider=name,
                error=result.error,
                reason=result.failure_reason.value if result.failure_reason else None,
            )

        # Whole chain exhausted — return aggregate failure.
        return ImageGenResult(
            images=[],
            provider=last_provider or self._providers[0][1].provider_name,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=last_error or "all_providers_unavailable",
            failure_reason=last_reason or FailureReason.PROVIDER_UNAVAILABLE,
        )

    async def aclose(self) -> None:
        for _, provider in self._providers:
            close_method = getattr(provider, "aclose", None)
            if close_method:
                try:
                    await close_method()
                except Exception:
                    logger.warning(
                        "design_provider_close_failed",
                        provider=type(provider).__name__,
                    )
