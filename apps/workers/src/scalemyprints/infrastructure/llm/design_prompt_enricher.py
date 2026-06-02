"""
LLM-based design prompt enricher.

Takes a user's raw prompt + style + aspect and returns a production-grade
prompt optimized for image-gen models (Flux, DALL-E, SDXL).

We rely on a templated prompt (style preset + universal POD hints) and
optionally call OpenAI to expand short prompts into rich, specific
descriptions. When OpenAI is unavailable we fall back to pure template
composition — the result is still good, just less specific.

Adapter never raises — returns PromptEnrichmentResult with `error` on
LLM failure (the fallback prompt is still returned in `enriched_prompt`).
"""

from __future__ import annotations

import contextlib
import json
import time

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStyle,
    OutputFormat,
)
from scalemyprints.domain.design.ports import PromptEnrichmentResult
from scalemyprints.domain.design.style_presets import (
    POD_GLOBAL_NEGATIVE,
    POD_GLOBAL_POSITIVE_HINTS,
    STYLE_PRESETS,
)

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a Print-on-Demand design prompt engineer.

Take the user's raw idea and rewrite it into a single rich image-gen
prompt that:

  • Names the concrete subject + composition + colour palette
  • Reinforces the requested STYLE preset (vintage/minimal/etc.)
  • Hints at print-on-demand requirements (centered, transparent
    background unless inappropriate, crisp readable type if any)
  • Avoids copyrighted entities (Disney, Marvel, sports teams,
    celebrity names, song lyrics, character likenesses)
  • Avoids real-person faces unless explicitly requested
  • Is 1-3 sentences, no bullet lists, no quotation marks

Return STRICT JSON:
  {"prompt": "...", "negative_prompt": "..."}

The negative_prompt should add domain-specific exclusions on top of
the global POD negatives — keep it short (1 sentence)."""


USER_TEMPLATE = """Raw idea: "{raw}"
Style preset: {style_label} — {style_description}
Aspect: {aspect}
Output format: {output_format}
{user_negative}

Style fragment to include verbatim or paraphrased: "{style_positive}"
Style negatives to extend: "{style_negative}"

Rewrite into a production-quality image-gen prompt."""


def _compose_template_only(
    *,
    raw_prompt: str,
    style: DesignStyle,
    output_format: OutputFormat,
    user_negative: str | None,
) -> tuple[str, str]:
    """Pure-template fallback when no LLM is available."""
    preset = STYLE_PRESETS[style]
    transparent_hint = (
        "transparent background, isolated subject, "
        if output_format == OutputFormat.PNG_TRANSPARENT
        else ""
    )

    enriched = (
        f"{raw_prompt.strip()}, {preset.positive_fragment}. "
        f"{transparent_hint}{POD_GLOBAL_POSITIVE_HINTS}."
    )
    negative_parts = [POD_GLOBAL_NEGATIVE, preset.negative_fragment]
    if user_negative:
        negative_parts.append(user_negative.strip())
    negative = ", ".join(negative_parts)
    return enriched, negative


class TemplateOnlyDesignPromptEnricher:
    """No-LLM enricher — composes template fragments only."""

    async def enrich(
        self,
        *,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        negative_prompt: str | None = None,
    ) -> PromptEnrichmentResult:
        start = time.monotonic()
        enriched, negative = _compose_template_only(
            raw_prompt=raw_prompt,
            style=style,
            output_format=output_format,
            user_negative=negative_prompt,
        )
        return PromptEnrichmentResult(
            enriched_prompt=enriched,
            negative_prompt=negative,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=None,
        )


class OpenAIDesignPromptEnricher:
    """OpenAI-powered prompt enricher with template fallback."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 15.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    async def enrich(
        self,
        *,
        raw_prompt: str,
        style: DesignStyle,
        aspect: DesignAspect,
        output_format: OutputFormat,
        negative_prompt: str | None = None,
    ) -> PromptEnrichmentResult:
        start = time.monotonic()
        preset = STYLE_PRESETS[style]
        log = logger.bind(service="design_prompt_enricher", style=style.value)

        # Always compute the fallback first — we return it on LLM failure.
        fallback_prompt, fallback_negative = _compose_template_only(
            raw_prompt=raw_prompt,
            style=style,
            output_format=output_format,
            user_negative=negative_prompt,
        )

        if not self._api_key:
            return PromptEnrichmentResult(
                enriched_prompt=fallback_prompt,
                negative_prompt=fallback_negative,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="no_api_key",
            )

        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
        except ImportError:
            return PromptEnrichmentResult(
                enriched_prompt=fallback_prompt,
                negative_prompt=fallback_negative,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="openai_lib_missing",
            )

        client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        user_msg = USER_TEMPLATE.format(
            raw=raw_prompt.strip()[:600],
            style_label=preset.label,
            style_description=preset.description,
            style_positive=preset.positive_fragment,
            style_negative=preset.negative_fragment,
            aspect=aspect.value,
            output_format=output_format.value,
            user_negative=(
                f'User-supplied negative: "{negative_prompt.strip()}"' if negative_prompt else ""
            ),
        )

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                response_format={"type": "json_object"},
                temperature=0.6,
                max_tokens=400,
            )
        except Exception as e:
            log.warning("design_enrichment_llm_error", error=str(e)[:200])
            return PromptEnrichmentResult(
                enriched_prompt=fallback_prompt,
                negative_prompt=fallback_negative,
                duration_ms=int((time.monotonic() - start) * 1000),
                error=f"llm_error:{e.__class__.__name__}",
            )
        finally:
            with contextlib.suppress(Exception):
                await client.close()

        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            log.warning("design_enrichment_invalid_json")
            return PromptEnrichmentResult(
                enriched_prompt=fallback_prompt,
                negative_prompt=fallback_negative,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="invalid_json_response",
            )

        llm_prompt = (parsed.get("prompt") or "").strip()
        llm_negative = (parsed.get("negative_prompt") or "").strip()

        if not llm_prompt:
            return PromptEnrichmentResult(
                enriched_prompt=fallback_prompt,
                negative_prompt=fallback_negative,
                duration_ms=int((time.monotonic() - start) * 1000),
                error="empty_llm_prompt",
            )

        # Compose with global POD hints + user negative — LLM might miss them.
        final_prompt = f"{llm_prompt} {POD_GLOBAL_POSITIVE_HINTS}."
        negative_parts = [POD_GLOBAL_NEGATIVE]
        if llm_negative:
            negative_parts.append(llm_negative)
        if negative_prompt:
            negative_parts.append(negative_prompt.strip())
        final_negative = ", ".join(negative_parts)

        duration_ms = int((time.monotonic() - start) * 1000)
        log.info("design_enrichment_complete", duration_ms=duration_ms)
        return PromptEnrichmentResult(
            enriched_prompt=final_prompt,
            negative_prompt=final_negative,
            duration_ms=duration_ms,
            error=None,
        )
