"""ImageGenProviderChain — fall-through, terminal-failure short-circuit, breaker."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    FailureReason,
    OutputFormat,
)
from scalemyprints.infrastructure.image_gen.provider_chain import (
    ImageGenProviderChain,
)
from scalemyprints.infrastructure.trademark_apis.circuit_breaker import (
    CircuitBreakerConfig,
)
from tests.domain.design.conftest import StubImageGenProvider, build_generated_image


def _kwargs() -> dict:
    return {
        "enriched_prompt": "p",
        "raw_prompt": "p",
        "style": DesignStyle.MINIMAL,
        "aspect": DesignAspect.SQUARE,
        "output_format": OutputFormat.PNG_TRANSPARENT,
        "variant_count": 1,
    }


@pytest.mark.unit
class TestImageGenProviderChain:
    async def test_first_success_wins(self) -> None:
        first = StubImageGenProvider(images=[build_generated_image()])
        second = StubImageGenProvider(images=[build_generated_image()])
        chain = ImageGenProviderChain([("first", first), ("second", second)])

        result = await chain.generate(**_kwargs())

        assert result.images
        assert first.calls == 1
        assert second.calls == 0  # never reached

    async def test_falls_through_on_provider_unavailable(self) -> None:
        first = StubImageGenProvider(
            images=[],
            error="timeout",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
        second = StubImageGenProvider(images=[build_generated_image()])
        chain = ImageGenProviderChain([("first", first), ("second", second)])

        result = await chain.generate(**_kwargs())

        assert result.images
        assert first.calls == 1
        assert second.calls == 1

    async def test_short_circuits_on_policy_violation(self) -> None:
        first = StubImageGenProvider(
            images=[],
            error="content_policy",
            failure_reason=FailureReason.POLICY_VIOLATION,
        )
        second = StubImageGenProvider(images=[build_generated_image()])
        chain = ImageGenProviderChain([("first", first), ("second", second)])

        result = await chain.generate(**_kwargs())

        assert not result.images
        assert result.failure_reason == FailureReason.POLICY_VIOLATION
        # Second provider not called — same prompt would fail there too.
        assert second.calls == 0

    async def test_all_providers_failing_returns_aggregate_error(self) -> None:
        first = StubImageGenProvider(
            images=[],
            error="timeout",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
        second = StubImageGenProvider(
            images=[],
            error="timeout",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
        chain = ImageGenProviderChain([("first", first), ("second", second)])

        result = await chain.generate(**_kwargs())

        assert not result.images
        assert result.failure_reason == FailureReason.PROVIDER_UNAVAILABLE

    async def test_breaker_opens_after_threshold(self) -> None:
        first = StubImageGenProvider(
            images=[],
            error="timeout",
            failure_reason=FailureReason.PROVIDER_UNAVAILABLE,
        )
        second = StubImageGenProvider(images=[build_generated_image()])
        chain = ImageGenProviderChain(
            [("first", first), ("second", second)],
            breaker_config=CircuitBreakerConfig(
                failure_threshold=2,
                cooldown_seconds=60,
            ),
        )

        # Two calls open the breaker on `first`.
        await chain.generate(**_kwargs())
        await chain.generate(**_kwargs())
        # Third call: `first` is short-circuited; second still answers.
        await chain.generate(**_kwargs())

        # `first` was attempted only twice — third call skipped it.
        assert first.calls == 2
        assert second.calls == 3
