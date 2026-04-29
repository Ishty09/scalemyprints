"""Tests for GenericnessCalculator."""

from __future__ import annotations

import pytest

from scalemyprints.domain.trademark.genericness import GenericnessCalculator


@pytest.fixture
def calculator() -> GenericnessCalculator:
    return GenericnessCalculator()


class TestGenericnessCalculator:
    def test_empty_phrase_returns_zero(self, calculator: GenericnessCalculator) -> None:
        assert calculator.calculate("") == 0.0

    def test_whitespace_only_returns_zero(self, calculator: GenericnessCalculator) -> None:
        assert calculator.calculate("   ") == 0.0

    def test_fully_generic_phrase_scores_high(self, calculator: GenericnessCalculator) -> None:
        # All words in GENERIC_MARKERS
        score = calculator.calculate("best mom life")
        assert score >= 0.8

    def test_highly_distinctive_phrase_scores_low(self, calculator: GenericnessCalculator) -> None:
        # Arbitrary coined word — no generic markers
        score = calculator.calculate("Xyzqla")
        assert score == 0.0

    def test_mixed_phrase_scores_in_middle(self, calculator: GenericnessCalculator) -> None:
        # "Best" is generic, "Spotify" isn't
        score = calculator.calculate("Best Spotify")
        assert 0.2 < score < 0.7

    def test_case_insensitive(self, calculator: GenericnessCalculator) -> None:
        lower = calculator.calculate("best mom life")
        upper = calculator.calculate("BEST MOM LIFE")
        mixed = calculator.calculate("Best Mom Life")
        assert lower == upper == mixed

    def test_punctuation_ignored(self, calculator: GenericnessCalculator) -> None:
        with_punct = calculator.calculate("Best Mom, Life!")
        without = calculator.calculate("Best Mom Life")
        assert with_punct == without

    def test_output_is_clamped_0_to_1(self, calculator: GenericnessCalculator) -> None:
        # Even for extreme inputs, should never exceed [0, 1]
        score = calculator.calculate("best best best best best")
        assert 0.0 <= score <= 1.0

    def test_common_pod_phrase_dog_mom(self, calculator: GenericnessCalculator) -> None:
        # "dog mom" — both in generic markers → very high
        score = calculator.calculate("dog mom")
        assert score >= 0.7

    def test_common_pod_phrase_teacher_life(self, calculator: GenericnessCalculator) -> None:
        score = calculator.calculate("teacher life")
        assert score >= 0.7

    def test_longer_distinctive_phrase_dilutes_generic_words(
        self, calculator: GenericnessCalculator
    ) -> None:
        # "best" + 4 unknown words → less generic than "best" alone
        short = calculator.calculate("best")
        long = calculator.calculate("best Algernon Wellington chronomorphic")
        assert long < short
