"""
Design Engine — domain enums.

Style presets are deliberately curated for POD (vintage/typography/etc).
Aspect ratios match common print products (square = sticker/sq art,
portrait = phone case, landscape = mug wrap, t_shirt = chest print).
"""

from __future__ import annotations

from enum import StrEnum


class DesignStyle(StrEnum):
    """Curated style presets for POD designs."""

    VINTAGE = "vintage"
    MINIMAL = "minimal"
    BOLD_TYPOGRAPHY = "bold_typography"
    VECTOR = "vector"
    RETRO_80S = "retro_80s"
    KAWAII = "kawaii"
    HAND_DRAWN = "hand_drawn"
    WATERCOLOR = "watercolor"
    LINE_ART = "line_art"
    CYBERPUNK = "cyberpunk"
    BOHO = "boho"
    DISTRESSED = "distressed"


class DesignAspect(StrEnum):
    """Aspect ratios — chosen to match POD product surfaces."""

    SQUARE = "square"  # 1:1 — stickers, sq prints, social
    PORTRAIT = "portrait"  # 2:3 — phone cases, posters
    LANDSCAPE = "landscape"  # 3:2 — mug wraps, banners
    T_SHIRT = "t_shirt"  # 4:5 — chest print area


class DesignStatus(StrEnum):
    """Lifecycle states of a design job."""

    QUEUED = "queued"
    ENRICHING = "enriching"
    GENERATING = "generating"
    POST_PROCESSING = "post_processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OutputFormat(StrEnum):
    """Output file format for the rendered design."""

    PNG = "png"
    PNG_TRANSPARENT = "png_transparent"
    WEBP = "webp"


class ImageGenProviderName(StrEnum):
    """Concrete image-gen providers that can be wired into the chain."""

    DISABLED = "disabled"
    FAL_FLUX_SCHNELL = "fal_flux_schnell"
    FAL_FLUX_PRO = "fal_flux_pro"
    OPENAI_DALLE3 = "openai_dalle3"
    REPLICATE_SDXL = "replicate_sdxl"


class FailureReason(StrEnum):
    """Categorized error reasons surfaced to the UI / logs."""

    QUOTA_EXCEEDED = "quota_exceeded"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_RATE_LIMITED = "provider_rate_limited"
    POLICY_VIOLATION = "policy_violation"
    INVALID_PROMPT = "invalid_prompt"
    STORAGE_FAILURE = "storage_failure"
    INTERNAL = "internal"
