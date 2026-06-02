"""DisabledImageGenProvider — always errors out cleanly."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    FailureReason,
    ImageGenProviderName,
    OutputFormat,
)
from scalemyprints.infrastructure.image_gen.disabled import DisabledImageGenProvider


@pytest.mark.unit
async def test_disabled_provider_returns_unavailable() -> None:
    adapter = DisabledImageGenProvider()
    assert adapter.provider_name == ImageGenProviderName.DISABLED

    result = await adapter.generate(
        enriched_prompt="x",
        raw_prompt="x",
        style=DesignStyle.MINIMAL,
        aspect=DesignAspect.SQUARE,
        output_format=OutputFormat.PNG_TRANSPARENT,
        variant_count=1,
    )

    assert result.images == []
    assert result.error == "image_gen_disabled"
    assert result.failure_reason == FailureReason.PROVIDER_UNAVAILABLE
