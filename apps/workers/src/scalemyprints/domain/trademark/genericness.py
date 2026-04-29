"""
Phrase genericness calculator.

A "generic" or "descriptive" phrase is one that ordinary language uses
without any distinctive branding meaning (e.g., "best coffee mug", "mom life").
Such phrases are HARDER to trademark and SAFER to use commercially.

A "distinctive" phrase is arbitrary or fanciful ("Spotify", "Kodak") and
is EASIER to trademark — meaning higher risk if someone else has it.

This heuristic returns 0.0 - 1.0 where:
- 0.0 = highly distinctive (coined word, arbitrary)
- 1.0 = highly generic (common words, descriptive phrase)

Phase A: simple word-list heuristic. Can be upgraded to ML classifier later.
"""

from __future__ import annotations

import re

# Common English words that commonly appear in generic/descriptive phrases.
# These are signals of genericness — each match raises the score.
GENERIC_MARKERS: frozenset[str] = frozenset({
    # Superlatives
    "best", "greatest", "ultimate", "amazing", "awesome", "perfect",
    "great", "good", "cool", "nice", "lovely", "beautiful",

    # Feelings / vibes
    "love", "hate", "happy", "sad", "blessed", "grateful", "joyful",
    "vibes", "mood", "energy", "era", "life", "living", "lifestyle",

    # Family / roles
    "mom", "dad", "mama", "papa", "mother", "father", "grandma",
    "grandpa", "nana", "mommy", "daddy", "parent", "sister", "brother",
    "aunt", "uncle", "cousin", "wife", "husband", "girlfriend", "boyfriend",

    # Professions (common POD niches)
    "teacher", "nurse", "doctor", "engineer", "programmer", "designer",
    "student", "farmer", "mechanic", "electrician", "firefighter", "police",

    # Pronouns / determiners
    "the", "my", "your", "our", "their", "his", "her", "its", "this",
    "that", "these", "those",

    # Common modifiers
    "cute", "funny", "simple", "easy", "new", "old", "big", "small",
    "classic", "vintage", "modern", "retro", "fresh", "rare",

    # Descriptors
    "style", "club", "crew", "team", "gang", "squad", "tribe", "family",

    # Hobbies / interests
    "coffee", "tea", "wine", "beer", "dog", "cat", "pet", "plant",
    "book", "music", "art", "craft", "travel", "beach", "mountain",

    # Time / seasonal
    "summer", "winter", "spring", "fall", "autumn", "christmas", "easter",
    "halloween", "birthday", "anniversary", "weekend",
})

# Tokenizer: ASCII letters only. For Phase A we target English-language
# phrases used in US/EU/UK/AU POD markets; unicode support can be added later
# via the `regex` package if needed.
_TOKEN_RE = re.compile(r"[a-zA-Z]+")


class GenericnessCalculator:
    """
    Estimates how generic/descriptive a phrase is.

    Pure function wrapped in a class for injection/mocking in tests.
    """

    def calculate(self, phrase: str) -> float:
        """
        Return genericness score 0.0-1.0.

        Algorithm (Phase A heuristic):
        1. Tokenize to words
        2. Ratio of generic-marker words to total
        3. Adjust for phrase length (shorter phrases with generic words = more generic)
        """
        words = self._tokenize(phrase)
        if not words:
            return 0.0

        generic_count = sum(1 for w in words if w in GENERIC_MARKERS)
        ratio = generic_count / len(words)

        # Very short phrases (1-2 words) with ALL generic words are clearly generic
        # Longer phrases dilute the signal
        length_factor = 1.0 if len(words) <= 3 else 0.8

        score = ratio * length_factor
        return max(0.0, min(1.0, score))

    @staticmethod
    def _tokenize(phrase: str) -> list[str]:
        """Lowercase tokenize, keeping only ASCII letter sequences."""
        return _TOKEN_RE.findall(phrase.lower())
