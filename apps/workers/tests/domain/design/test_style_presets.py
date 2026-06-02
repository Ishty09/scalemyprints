"""Style preset table — every DesignStyle has a preset; aspect specs cover all aspects."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.enums import DesignAspect, DesignStyle
from scalemyprints.domain.design.style_presets import (
    ASPECT_SPECS,
    POD_GLOBAL_NEGATIVE,
    POD_GLOBAL_POSITIVE_HINTS,
    STYLE_PRESETS,
)


@pytest.mark.unit
class TestStylePresets:
    def test_every_style_has_a_preset(self) -> None:
        for style in DesignStyle:
            assert style in STYLE_PRESETS, f"missing preset for {style}"

    def test_presets_have_non_empty_fragments(self) -> None:
        for style, preset in STYLE_PRESETS.items():
            assert preset.label
            assert preset.description
            assert preset.positive_fragment
            assert preset.negative_fragment
            assert preset.style == style

    def test_global_negative_includes_copyright_terms(self) -> None:
        assert "copyrighted" in POD_GLOBAL_NEGATIVE.lower()
        assert "watermark" in POD_GLOBAL_NEGATIVE.lower()

    def test_global_positive_mentions_pod(self) -> None:
        assert "print-on-demand" in POD_GLOBAL_POSITIVE_HINTS.lower()


@pytest.mark.unit
class TestAspectSpecs:
    def test_every_aspect_has_a_spec(self) -> None:
        for aspect in DesignAspect:
            assert aspect in ASPECT_SPECS

    def test_dimensions_match_ratio_label(self) -> None:
        sq = ASPECT_SPECS[DesignAspect.SQUARE]
        assert sq.width == sq.height
        assert sq.ratio_label == "1:1"

        portrait = ASPECT_SPECS[DesignAspect.PORTRAIT]
        assert portrait.height > portrait.width

        landscape = ASPECT_SPECS[DesignAspect.LANDSCAPE]
        assert landscape.width > landscape.height
