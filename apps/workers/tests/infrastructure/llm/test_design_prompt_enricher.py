"""Design prompt enricher — template-only mode + LLM fallback."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    OutputFormat,
)
from scalemyprints.infrastructure.llm.design_prompt_enricher import (
    OpenAIDesignPromptEnricher,
    TemplateOnlyDesignPromptEnricher,
)


@pytest.mark.unit
class TestTemplateOnlyDesignPromptEnricher:
    async def test_enriches_with_style_fragment(self) -> None:
        enricher = TemplateOnlyDesignPromptEnricher()
        result = await enricher.enrich(
            raw_prompt="dog mom with iced coffee",
            style=DesignStyle.MINIMAL,
            aspect=DesignAspect.SQUARE,
            output_format=OutputFormat.PNG_TRANSPARENT,
        )
        assert result.error is None
        assert "dog mom with iced coffee" in result.enriched_prompt
        assert "minimal" in result.enriched_prompt.lower()
        assert "transparent" in result.enriched_prompt.lower()

    async def test_negative_prompt_includes_global_negatives(self) -> None:
        enricher = TemplateOnlyDesignPromptEnricher()
        result = await enricher.enrich(
            raw_prompt="dog",
            style=DesignStyle.VINTAGE,
            aspect=DesignAspect.SQUARE,
            output_format=OutputFormat.PNG,
        )
        assert result.negative_prompt is not None
        assert "watermark" in result.negative_prompt
        assert "copyrighted" in result.negative_prompt

    async def test_user_negative_appended(self) -> None:
        enricher = TemplateOnlyDesignPromptEnricher()
        result = await enricher.enrich(
            raw_prompt="dog",
            style=DesignStyle.MINIMAL,
            aspect=DesignAspect.SQUARE,
            output_format=OutputFormat.PNG,
            negative_prompt="text, words, gradient",
        )
        assert "text, words, gradient" in (result.negative_prompt or "")


@pytest.mark.unit
class TestOpenAIDesignPromptEnricherFallback:
    async def test_no_api_key_returns_template_fallback(self) -> None:
        enricher = OpenAIDesignPromptEnricher(api_key="")
        result = await enricher.enrich(
            raw_prompt="dog",
            style=DesignStyle.MINIMAL,
            aspect=DesignAspect.SQUARE,
            output_format=OutputFormat.PNG_TRANSPARENT,
        )
        assert result.error == "no_api_key"
        # Still returns a workable prompt — orchestrator can proceed.
        assert "dog" in result.enriched_prompt
        assert result.negative_prompt
