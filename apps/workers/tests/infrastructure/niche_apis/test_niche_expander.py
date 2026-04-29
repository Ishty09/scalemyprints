"""Tests for OpenAI niche expander sanitization (no real API calls)."""

from __future__ import annotations

import pytest

from scalemyprints.domain.niche.enums import Country
from scalemyprints.infrastructure.llm.niche_expander import (
    OpenAINicheExpander,
    _sanitize_suggestions,
)


class TestSanitizeSuggestions:
    def test_filters_disney(self):
        raw = ["mickey mouse shirt", "dog mom mug", "disney shirt", "cat dad"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert "disney shirt" not in cleaned
        # Note: "mickey mouse" is also copyright but not in our pattern - real LLM should self-filter
        assert "dog mom mug" in cleaned

    def test_filters_marvel(self):
        raw = ["marvel comics tee", "spider lover", "comic book"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert not any("marvel" in s.lower() for s in cleaned)

    def test_filters_sports_leagues(self):
        raw = ["nfl jersey", "nba shirt", "soccer mom", "basketball dad"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert "nfl jersey" not in cleaned
        assert "nba shirt" not in cleaned
        assert "soccer mom" in cleaned  # generic OK

    def test_dedupes(self):
        raw = ["dog mom", "dog mom", "Dog Mom", "DOG MOM"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert len(cleaned) == 1

    def test_filters_too_short(self):
        raw = ["a", "ab", "abc", "abcd"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert "a" not in cleaned
        assert "ab" not in cleaned
        assert "abc" in cleaned

    def test_filters_too_long(self):
        long_str = "a" * 100
        raw = [long_str, "normal niche"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert long_str not in cleaned
        assert "normal niche" in cleaned

    def test_caps_at_max(self):
        raw = [f"niche {i}" for i in range(50)]
        cleaned = _sanitize_suggestions(raw, max_count=10)
        assert len(cleaned) == 10

    def test_filters_non_strings(self):
        raw = ["valid niche", 123, None, ["nested"], "another niche"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert len(cleaned) == 2

    def test_lowercases_output(self):
        raw = ["DOG MOM", "Cat Dad"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert "dog mom" in cleaned
        assert "cat dad" in cleaned

    def test_filters_harry_potter(self):
        raw = ["harry potter wand", "magic shirt"]
        cleaned = _sanitize_suggestions(raw, max_count=20)
        assert not any("harry potter" in s.lower() for s in cleaned)


class TestOpenAINicheExpander:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_error(self):
        expander = OpenAINicheExpander(api_key="")
        result = await expander.expand("dog mom", Country.US)
        assert result.error == "no_api_key"
        assert result.suggestions == []
