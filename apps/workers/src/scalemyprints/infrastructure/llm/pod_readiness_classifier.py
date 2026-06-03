"""
POD-readiness classifier — given a phrase (typically a viral signal),
return a 0–100 score for how likely it is to become a profitable POD
listing, plus suggested design styles.

Two implementations:
- `OpenAIPODReadinessClassifier` — uses gpt-4o-mini (cheap, fast).
  Returns structured JSON with `score`, `reasoning`, `styles`.
- `HeuristicPODReadinessClassifier` — fallback when no OpenAI key
  is configured. Uses keyword heuristics on the phrase.

Adapter never raises. Always returns a populated result; falls back
to the heuristic if the LLM call fails.
"""

from __future__ import annotations

import json
import re
import time
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger

logger = get_logger(__name__)


class PODReadinessResult(BaseModel):
    """Per-phrase classification output."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    reasoning: str
    suggested_styles: list[str] = Field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


@runtime_checkable
class PODReadinessClassifier(Protocol):
    """Score a phrase for POD readiness."""

    async def classify(self, phrase: str) -> PODReadinessResult: ...

    async def classify_batch(
        self,
        phrases: list[str],
    ) -> list[PODReadinessResult]: ...


# -----------------------------------------------------------------------------
# Heuristic classifier (fallback)
# -----------------------------------------------------------------------------


# POD-friendly signal keywords. Order doesn't matter; each match adds
# weight. Negative-signal keywords subtract.
_POSITIVE = {
    "mom": 8, "dad": 8, "teacher": 10, "nurse": 12, "engineer": 6,
    "coffee": 7, "wine": 7, "cat": 9, "dog": 9, "puppy": 6,
    "christmas": 12, "halloween": 12, "valentine": 9, "easter": 8,
    "birthday": 6, "grandma": 8, "grandpa": 8, "aunt": 5, "uncle": 5,
    "funny": 9, "vintage": 7, "retro": 6, "cute": 7, "minimalist": 6,
    "boho": 6, "cottagecore": 7, "y2k": 5, "kawaii": 7,
    "gym": 6, "yoga": 6, "vegan": 5, "plant": 5, "succulent": 4,
    "boss": 6, "wife": 6, "husband": 6, "girlfriend": 5, "boyfriend": 5,
    "graduation": 7, "wedding": 7, "anniversary": 5,
}
_NEGATIVE = {
    "porn": -100, "nude": -80, "drug": -60, "kill": -40, "murder": -40,
    "politics": -20, "election": -20, "religion": -10, "racist": -100,
    "tutorial": -15, "review": -15, "podcast": -10, "news": -15,
    "stream": -15, "subscribe": -15, "tiktok": -10, "tweet": -15,
    "amazon": -15, "shopify": -15, "ebay": -15,
}

_WORD_RE = re.compile(r"[A-Za-z']+")


class HeuristicPODReadinessClassifier(PODReadinessClassifier):
    """Cheap keyword-driven classifier — no LLM call, fully local."""

    async def classify(self, phrase: str) -> PODReadinessResult:
        start = time.monotonic()
        words = {w.lower() for w in _WORD_RE.findall(phrase or "")}
        if not words:
            return PODReadinessResult(
                score=0,
                reasoning="empty phrase",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        # Sum signals; map to 0-100.
        raw = 30  # neutral floor
        positives_matched: list[str] = []
        for w in words:
            if w in _POSITIVE:
                raw += _POSITIVE[w]
                positives_matched.append(w)
            if w in _NEGATIVE:
                raw += _NEGATIVE[w]

        # Length penalty — very short phrases are too vague
        if len(words) <= 1:
            raw -= 10

        score = max(0, min(100, raw))

        styles = _suggest_styles(words)

        if positives_matched:
            reasoning = f"matched positive POD signals: {', '.join(positives_matched[:5])}"
        else:
            reasoning = "no strong POD signals; default low score"

        return PODReadinessResult(
            score=score,
            reasoning=reasoning,
            suggested_styles=styles,
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    async def classify_batch(self, phrases: list[str]) -> list[PODReadinessResult]:
        out: list[PODReadinessResult] = []
        for p in phrases:
            out.append(await self.classify(p))
        return out


def _suggest_styles(words: set[str]) -> list[str]:
    styles: list[str] = []
    if any(w in words for w in ("cat", "dog", "puppy")):
        styles.append("kawaii")
        styles.append("watercolor")
    if any(w in words for w in ("vintage", "retro")):
        styles.append("vintage")
        styles.append("distressed")
    if any(w in words for w in ("christmas", "halloween", "easter")):
        styles.append("vintage")
        styles.append("bold_typography")
    if any(w in words for w in ("minimalist", "boho", "yoga")):
        styles.append("minimal")
        styles.append("line_art")
    if not styles:
        styles = ["minimal", "bold_typography"]
    return list(dict.fromkeys(styles))[:4]


# -----------------------------------------------------------------------------
# OpenAI-backed classifier (production)
# -----------------------------------------------------------------------------


_SYSTEM_PROMPT = """You are a print-on-demand market analyst. Given a phrase
(a meme, niche term, trending hashtag, or POD design concept), output a
JSON object with:

  - "score": integer 0-100 estimating how viable this phrase is as a POD
    product (t-shirt, mug, sticker). Consider: clarity, emotional pull,
    target audience size, evergreen vs. flash trend, trademark risk.
  - "reasoning": 1 sentence explaining the score.
  - "suggested_styles": list of 2-4 design styles from this allowlist
    only: ["minimal","bold_typography","vintage","vector","retro_80s",
    "kawaii","hand_drawn","watercolor","line_art","cyberpunk","boho",
    "distressed"].

Score harshly. Most random hashtags should score 30-50. A reserve
80+ for phrases that you genuinely believe would sell on Etsy.

Return ONLY the JSON object, no markdown, no preamble."""


class OpenAIPODReadinessClassifier(PODReadinessClassifier):
    """Production classifier backed by gpt-4o-mini."""

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
        self._fallback = HeuristicPODReadinessClassifier()

    async def classify(self, phrase: str) -> PODReadinessResult:
        start = time.monotonic()
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415
        except ImportError:
            return await self._fallback.classify(phrase)

        client = AsyncOpenAI(api_key=self._api_key, timeout=self._timeout)
        try:
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"PHRASE: {phrase}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=200,
            )
        except Exception as e:
            logger.warning("openai_pod_readiness_failed_falling_back", error=str(e))
            return await self._fallback.classify(phrase)

        try:
            raw = resp.choices[0].message.content or "{}"
            parsed = json.loads(raw)
            score = int(parsed.get("score", 0))
            score = max(0, min(100, score))
            reasoning = str(parsed.get("reasoning", ""))[:400]
            styles = parsed.get("suggested_styles") or []
            if not isinstance(styles, list):
                styles = []
            styles = [str(s) for s in styles if isinstance(s, str)][:4]
            return PODReadinessResult(
                score=score,
                reasoning=reasoning,
                suggested_styles=styles,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            logger.warning("openai_pod_readiness_parse_failed", error=str(e))
            return await self._fallback.classify(phrase)

    async def classify_batch(self, phrases: list[str]) -> list[PODReadinessResult]:
        # Naive batching — could be parallelized via asyncio.gather but
        # OpenAI's rate limits make sequential safer here.
        out: list[PODReadinessResult] = []
        for p in phrases:
            out.append(await self.classify(p))
        return out
