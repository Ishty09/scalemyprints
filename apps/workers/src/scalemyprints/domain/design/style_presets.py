"""
Style preset definitions.

Each style maps to a curated prompt fragment + negative-prompt fragment
proven to produce on-brand POD designs. These get composed into the
final enriched prompt by PromptEnricher.

This is pure data (no behavior); kept in domain so adapters and the
LLM-based enricher can both reference the same vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass

from scalemyprints.domain.design.enums import DesignAspect, DesignStyle


@dataclass(frozen=True, slots=True)
class StylePreset:
    """One style preset with prompt + negative fragments."""

    style: DesignStyle
    label: str
    description: str
    positive_fragment: str
    negative_fragment: str


STYLE_PRESETS: dict[DesignStyle, StylePreset] = {
    DesignStyle.VINTAGE: StylePreset(
        style=DesignStyle.VINTAGE,
        label="Vintage",
        description="Retro print with aged paper texture and earthy tones.",
        positive_fragment=(
            "vintage-style illustration, aged paper texture, faded ink, "
            "muted earth tones, retro typography, distressed edges, "
            "1970s screen-print aesthetic"
        ),
        negative_fragment="modern, glossy, neon, photorealistic, 3d render",
    ),
    DesignStyle.MINIMAL: StylePreset(
        style=DesignStyle.MINIMAL,
        label="Minimal",
        description="Clean, simple, lots of negative space.",
        positive_fragment=(
            "minimal flat design, clean lines, ample negative space, "
            "limited 2-3 colour palette, simple shapes, modern, "
            "high-contrast composition"
        ),
        negative_fragment="cluttered, busy, photorealistic, gradient, 3d, drop shadow",
    ),
    DesignStyle.BOLD_TYPOGRAPHY: StylePreset(
        style=DesignStyle.BOLD_TYPOGRAPHY,
        label="Bold Typography",
        description="Big chunky letters as the hero of the design.",
        positive_fragment=(
            "bold typography hero design, thick sans-serif lettering, "
            "high contrast, layered text composition, t-shirt graphic, "
            "centered layout, crisp readable type"
        ),
        negative_fragment="thin font, hard-to-read script, watermark, lorem ipsum",
    ),
    DesignStyle.VECTOR: StylePreset(
        style=DesignStyle.VECTOR,
        label="Vector",
        description="Clean SVG-style flat illustration.",
        positive_fragment=(
            "flat vector illustration, solid fills, clean geometric shapes, "
            "no gradients, no texture, sticker-ready, cuttable outline, "
            "bold outlines"
        ),
        negative_fragment="photorealistic, gradient mesh, raster texture, blur, noise",
    ),
    DesignStyle.RETRO_80S: StylePreset(
        style=DesignStyle.RETRO_80S,
        label="Retro 80s",
        description="Synthwave neon, palm trees, sun-stripe energy.",
        positive_fragment=(
            "retro 80s synthwave aesthetic, neon magenta and cyan, sun stripes, "
            "chrome lettering, grid horizon, vaporwave, miami vice palette"
        ),
        negative_fragment="pastel, watercolor, hand-drawn",
    ),
    DesignStyle.KAWAII: StylePreset(
        style=DesignStyle.KAWAII,
        label="Kawaii",
        description="Cute pastel character with soft shading.",
        positive_fragment=(
            "kawaii cute character illustration, pastel palette, big sparkly eyes, "
            "rounded shapes, soft shading, sticker style, friendly expression"
        ),
        negative_fragment="dark, gritty, scary, photorealistic, anatomy errors",
    ),
    DesignStyle.HAND_DRAWN: StylePreset(
        style=DesignStyle.HAND_DRAWN,
        label="Hand-Drawn",
        description="Loose ink lines with hand-lettered feel.",
        positive_fragment=(
            "hand-drawn illustration, organic ink lines, slight imperfections, "
            "hand lettering, sketchy outline, cross-hatch shading"
        ),
        negative_fragment="vector clean, computer-perfect, 3d render",
    ),
    DesignStyle.WATERCOLOR: StylePreset(
        style=DesignStyle.WATERCOLOR,
        label="Watercolor",
        description="Soft watercolor washes with paper grain.",
        positive_fragment=(
            "watercolor painting, soft pigment washes, visible paper texture, "
            "delicate edges, translucent layers, hand-painted feel"
        ),
        negative_fragment="vector, hard edges, neon, 3d render, photoreal",
    ),
    DesignStyle.LINE_ART: StylePreset(
        style=DesignStyle.LINE_ART,
        label="Line Art",
        description="Continuous black line, no fills.",
        positive_fragment=(
            "single-line continuous line art, black lines on transparent, "
            "minimal contour drawing, no fills, elegant"
        ),
        negative_fragment="color fill, shading, photoreal, 3d",
    ),
    DesignStyle.CYBERPUNK: StylePreset(
        style=DesignStyle.CYBERPUNK,
        label="Cyberpunk",
        description="Glowing neon over dark futurism.",
        positive_fragment=(
            "cyberpunk illustration, glowing neon highlights on dark background, "
            "futuristic city, glitch elements, holographic accents, high-contrast"
        ),
        negative_fragment="pastel, soft, vintage paper, watercolor",
    ),
    DesignStyle.BOHO: StylePreset(
        style=DesignStyle.BOHO,
        label="Boho",
        description="Earthy moon, sun, plants, celestial line work.",
        positive_fragment=(
            "boho celestial illustration, earthy terracotta and sage palette, "
            "moon phases, sun rays, botanical elements, fine line accents"
        ),
        negative_fragment="neon, cyberpunk, glossy, 3d",
    ),
    DesignStyle.DISTRESSED: StylePreset(
        style=DesignStyle.DISTRESSED,
        label="Distressed",
        description="Cracked, weathered, vintage print finish.",
        positive_fragment=(
            "distressed print effect, cracked ink, weathered texture, "
            "rough edges, screen-print look, used vintage feel"
        ),
        negative_fragment="clean, glossy, vector flat, 3d",
    ),
}


# ---------------------------------------------------------------------------
# Aspect → resolution mapping (used by adapters + storage)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AspectSpec:
    """Pixel resolution for a design aspect at the canonical render size."""

    aspect: DesignAspect
    width: int
    height: int
    ratio_label: str  # e.g. "1:1", "2:3"


ASPECT_SPECS: dict[DesignAspect, AspectSpec] = {
    DesignAspect.SQUARE: AspectSpec(DesignAspect.SQUARE, 1024, 1024, "1:1"),
    DesignAspect.PORTRAIT: AspectSpec(DesignAspect.PORTRAIT, 1024, 1536, "2:3"),
    DesignAspect.LANDSCAPE: AspectSpec(DesignAspect.LANDSCAPE, 1536, 1024, "3:2"),
    DesignAspect.T_SHIRT: AspectSpec(DesignAspect.T_SHIRT, 1024, 1280, "4:5"),
}


# ---------------------------------------------------------------------------
# Universal POD negative prompt (always appended)
# ---------------------------------------------------------------------------

POD_GLOBAL_NEGATIVE = (
    "watermark, signature, logo, copyrighted character, trademarked logo, "
    "celebrity face, real person likeness, blurry, low quality, "
    "extra fingers, deformed hands, illegible scribbled text, "
    "lorem ipsum, gibberish letters, cropped, cut off"
)

POD_GLOBAL_POSITIVE_HINTS = (
    "print-on-demand ready, centered composition, transparent background, "
    "high-resolution, crisp edges"
)
