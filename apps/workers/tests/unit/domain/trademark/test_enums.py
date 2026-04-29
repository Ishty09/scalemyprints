"""Tests for domain.trademark.enums helpers."""

from __future__ import annotations

import pytest

from scalemyprints.domain.trademark.enums import (
    JurisdictionCode,
    RiskLevel,
    get_adjacent_classes,
    score_to_risk_level,
)


class TestScoreToRiskLevel:
    """score_to_risk_level must match TS scoreToRiskLevel exactly."""

    @pytest.mark.parametrize(
        "score,expected",
        [
            (0, RiskLevel.SAFE),
            (10, RiskLevel.SAFE),
            (20, RiskLevel.SAFE),
            (21, RiskLevel.LOW),
            (30, RiskLevel.LOW),
            (40, RiskLevel.LOW),
            (41, RiskLevel.MEDIUM),
            (50, RiskLevel.MEDIUM),
            (60, RiskLevel.MEDIUM),
            (61, RiskLevel.HIGH),
            (70, RiskLevel.HIGH),
            (80, RiskLevel.HIGH),
            (81, RiskLevel.CRITICAL),
            (95, RiskLevel.CRITICAL),
            (100, RiskLevel.CRITICAL),
        ],
    )
    def test_boundary_values(self, score: int, expected: RiskLevel) -> None:
        assert score_to_risk_level(score) == expected


class TestGetAdjacentClasses:
    def test_apparel_adjacents_include_textiles_and_bags(self) -> None:
        adjacent = get_adjacent_classes([25])
        assert 24 in adjacent  # textiles
        assert 18 in adjacent  # bags
        assert 14 in adjacent  # jewelry
        assert 25 not in adjacent  # target class itself excluded

    def test_drinkware_adjacents(self) -> None:
        adjacent = get_adjacent_classes([21])
        assert 20 in adjacent  # furniture
        assert 21 not in adjacent

    def test_multiple_targets_union_of_adjacents(self) -> None:
        adjacent = get_adjacent_classes([25, 21])
        # From 25
        assert 24 in adjacent or 18 in adjacent
        # From 21
        assert 20 in adjacent
        # Neither of the targets themselves
        assert 25 not in adjacent
        assert 21 not in adjacent

    def test_unknown_class_returns_empty(self) -> None:
        adjacent = get_adjacent_classes([99])
        assert len(adjacent) == 0


class TestJurisdictionCode:
    def test_all_codes_are_strings(self) -> None:
        for code in JurisdictionCode:
            assert isinstance(code.value, str)
            assert len(code.value) == 2
