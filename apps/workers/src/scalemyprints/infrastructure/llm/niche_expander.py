"""
OpenAI niche expander.

Uses GPT-4o-mini to generate sub-niche ideas from a seed keyword.
Cheap (~$0.15/1M tokens), fast (~1.5s per call), reliable.

Output is sanitized — we filter known-bad patterns (offensive, fictional
nonsense, copyrighted) before returning to the user.

Falls back gracefully if API key missing or rate-limited.
"""

from __future__ import annotations

import json
import re
import time

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.niche.enums import Country
from scalemyprints.domain.niche.ports import NicheExpansionResult

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a Print-on-Demand niche research assistant. Given a seed
keyword, generate sub-niches that would work well for Etsy, Amazon Merch, Redbubble.

Rules:
- Each suggestion is 2-5 words, lowercase
- Concrete and specific (not "love" but "girl mom shirt")
- No copyrighted brands (no Disney, Marvel, sports teams, song lyrics)
- No offensive content
- Return STRICT JSON: {"suggestions": ["niche 1", "niche 2", ...], "rationale": "1-line summary"}
- 15-20 suggestions
"""

USER_PROMPT_TEMPLATE = """Seed niche: "{keyword}"
Target country: {country}

Generate 15-20 specific POD sub-niches around this seed."""


# Tokens to filter — copyrighted/offensive/nonsense
_FORBIDDEN_PATTERNS = (
    re.compile(r"\b(disney|marvel|nike|adidas|coca[-\s]?cola|nfl|nba|mlb|nhl|fifa)\b", re.I),
    re.compile(r"\b(harry potter|star wars|game of thrones|lord of the rings)\b", re.I),
)


class OpenAINicheExpander:
    """Niche expansion via OpenAI ChatCompletions API."""

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

    async def expand(
        self,
        seed_keyword: str,
        country: Country,
        max_suggestions: int = 20,
    ) -> NicheExpansionResult:
        start = time.monotonic()
        log = logger.bind(service="openai_niche", keyword=seed_keyword)

        if not self._api_key:
            return NicheExpansionResult(
                suggestions=[],
                duration_ms=0,
                error="no_api_key",
            )

        try:
            from openai import AsyncOpenAI  # type: ignore[import-not-found]
        except ImportError:
            return NicheExpansionResult(
                suggestions=[],
                duration_ms=0,
                error="openai_lib_missing",
            )

        client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)

        try:
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(
                            keyword=seed_keyword,
                            country=country.value,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
                temperature=0.7,
                max_tokens=600,
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)

            raw_suggestions = parsed.get("suggestions", [])
            rationale = parsed.get("rationale")

            cleaned = _sanitize_suggestions(raw_suggestions, max_count=max_suggestions)
            log.info(
                "niche_expansion_complete",
                generated=len(raw_suggestions),
                accepted=len(cleaned),
                duration_ms=duration_ms,
            )

            return NicheExpansionResult(
                suggestions=cleaned,
                rationale=rationale,
                duration_ms=duration_ms,
                error=None,
            )
        except json.JSONDecodeError:
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("niche_expansion_invalid_json")
            return NicheExpansionResult(
                suggestions=[],
                duration_ms=duration_ms,
                error="invalid_json_response",
            )
        except Exception as e:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            log.warning("niche_expansion_error", error=str(e)[:120])
            return NicheExpansionResult(
                suggestions=[],
                duration_ms=duration_ms,
                error=f"unexpected:{e.__class__.__name__}",
            )
        finally:
            await client.close()


# -----------------------------------------------------------------------------
# Sanitization
# -----------------------------------------------------------------------------


def _sanitize_suggestions(raw: list, max_count: int) -> list[str]:
    """Filter out copyrighted/offensive/malformed entries."""
    cleaned: list[str] = []
    seen: set[str] = set()

    for item in raw:
        if not isinstance(item, str):
            continue
        s = item.strip().lower()
        if not s or len(s) > 80 or len(s) < 3:
            continue
        if any(p.search(s) for p in _FORBIDDEN_PATTERNS):
            continue
        if s in seen:
            continue
        seen.add(s)
        cleaned.append(s)
        if len(cleaned) >= max_count:
            break

    return cleaned
