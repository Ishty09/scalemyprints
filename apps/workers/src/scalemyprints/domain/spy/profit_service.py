"""
Profit calculator for POD listings.

Given (marketplace, product_type, sale_price, options), return the
expected per-unit profit factoring in:
- Base cost (Printful / Printify / Gelato / CustomCat / SPOD)
- Marketplace fee (Etsy 6.5%, Amazon Merch fixed royalty, Redbubble margin)
- Estimated ad spend (default 0; user can supply CPC × conv-rate)
- Shipping (when not included in sale_price)

Phase 2 ships static price tables — accurate as of 2026-Q2. A future
phase will swap in live Printful/Printify API pulls.

The math is intentionally exposed so users see exactly where their
money is going (the killer feature of "Profit, Honestly" tools).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.spy.enums import Marketplace

logger = get_logger(__name__)


ProductType = Literal[
    "t_shirt",
    "tank_top",
    "long_sleeve",
    "hoodie",
    "sweatshirt",
    "mug_11oz",
    "mug_15oz",
    "tote_bag",
    "phone_case",
    "poster_18x24",
    "sticker",
    "blanket_50x60",
    "pillow_18x18",
]


PrinterId = Literal["printful", "printify", "gelato", "customcat", "spod"]


# Base costs in USD per unit (US, no shipping). Sourced from each
# printer's public price list. Conservative estimates — pick the
# cheapest available SKU for each product type.
_BASE_COSTS_USD: dict[ProductType, dict[PrinterId, float]] = {
    "t_shirt":       {"printful": 11.95, "printify": 8.45,  "gelato": 12.50, "customcat": 9.95, "spod": 7.95},
    "tank_top":      {"printful": 12.95, "printify": 9.65,  "gelato": 13.00, "customcat": 11.95, "spod": 9.45},
    "long_sleeve":   {"printful": 17.95, "printify": 13.45, "gelato": 18.00, "customcat": 15.95, "spod": 13.95},
    "hoodie":        {"printful": 29.95, "printify": 22.85, "gelato": 31.00, "customcat": 27.95, "spod": 24.95},
    "sweatshirt":    {"printful": 26.95, "printify": 19.95, "gelato": 28.00, "customcat": 24.95, "spod": 21.95},
    "mug_11oz":      {"printful": 7.95,  "printify": 4.85,  "gelato": 8.50,  "customcat": 6.95,  "spod": 5.45},
    "mug_15oz":      {"printful": 9.95,  "printify": 6.85,  "gelato": 10.50, "customcat": 8.95,  "spod": 7.45},
    "tote_bag":      {"printful": 12.95, "printify": 9.95,  "gelato": 13.50, "customcat": 11.95, "spod": 10.95},
    "phone_case":    {"printful": 14.95, "printify": 11.45, "gelato": 16.00, "customcat": 13.95, "spod": 12.95},
    "poster_18x24":  {"printful": 11.50, "printify": 9.95,  "gelato": 14.00, "customcat": 10.95, "spod": 9.95},
    "sticker":       {"printful": 1.50,  "printify": 0.95,  "gelato": 2.00,  "customcat": 1.45,  "spod": 1.25},
    "blanket_50x60": {"printful": 34.95, "printify": 27.45, "gelato": 38.00, "customcat": 32.95, "spod": 30.95},
    "pillow_18x18":  {"printful": 17.95, "printify": 13.85, "gelato": 19.50, "customcat": 16.95, "spod": 15.95},
}


# Marketplace take-rate / royalty assumptions
# Etsy:  6.5% transaction fee + $0.20 listing + ~3% payment processing
# Amazon Merch: percentage of list price the seller receives (royalty)
#   varies by tier; we approximate using their 2026 published rates
#   for the $19.99 t-shirt → $4.78 royalty ≈ 24% of sale, but the
#   "royalty" model means cost+fees are deducted by Amazon. We model
#   it as "fee = sale_price * (1 - royalty_share)".
# Redbubble: artist gets (sale_price - base_cost) × margin%, where
#   margin defaults to 20% but can be set per artist. We model with
#   default 20%.

# Each lambda returns the FEE amount the platform takes (not what the
# seller keeps), in USD, given a sale_price.
_MARKETPLACE_FEE_FN = {
    # 6.5% transaction + 3% payment processing + $0.20 listing fee
    Marketplace.ETSY: lambda price: round(price * 0.065 + price * 0.03 + 0.20, 4),
    # Amazon Merch pays ~24% royalty → Amazon keeps 76%
    Marketplace.AMAZON_MERCH: lambda price: round(price * 0.76, 4),
    # Redbubble pays 20% artist margin → Redbubble keeps 80%
    Marketplace.REDBUBBLE: lambda price: round(price * 0.80, 4),
    # TeePublic 17% commission → keeps 83%
    Marketplace.TEEPUBLIC: lambda price: round(price * 0.83, 4),
    # Society6 10% commission → keeps 90%
    Marketplace.SOCIETY6: lambda price: round(price * 0.90, 4),
    # Zazzle 15% royalty → keeps 85%
    Marketplace.ZAZZLE: lambda price: round(price * 0.85, 4),
    # Spreadshirt 20% commission → keeps 80%
    Marketplace.SPREADSHIRT: lambda price: round(price * 0.80, 4),
    # Bonanza: 3.5% commission + $0.25 fee
    Marketplace.BONANZA: lambda price: round(price * 0.035 + 0.25, 4),
}


# Listing schemas ------------------------------------------------------


class ProfitInput(BaseModel):
    """Per-call profit inputs."""

    model_config = ConfigDict(extra="forbid")

    marketplace: Marketplace
    product_type: ProductType
    sale_price_usd: float = Field(gt=0)
    printer: PrinterId = "printify"             # default: cheapest mainstream
    shipping_usd: float = Field(default=0.0, ge=0.0)
    ad_cpc_usd: float = Field(default=0.0, ge=0.0)
    ad_conversion_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class ProfitBreakdown(BaseModel):
    """The exposed math — show users exactly where their money goes."""

    model_config = ConfigDict(frozen=True)

    sale_price_usd: float
    base_cost_usd: float
    marketplace_fee_usd: float
    shipping_usd: float
    ad_cost_usd: float
    profit_usd: float
    margin_pct: float
    printer: PrinterId
    note: str | None = None


def compute(payload: ProfitInput) -> ProfitBreakdown:
    """Per-unit profit math. Pure — no I/O."""
    base = _BASE_COSTS_USD.get(payload.product_type, {}).get(payload.printer)
    if base is None:
        # Fall back to printify's price for this product type if available
        base = _BASE_COSTS_USD.get(payload.product_type, {}).get("printify", 0.0)

    fee_fn = _MARKETPLACE_FEE_FN.get(payload.marketplace)
    if fee_fn is None:
        marketplace_fee = round(payload.sale_price_usd * 0.10, 4)
    else:
        marketplace_fee = round(fee_fn(payload.sale_price_usd), 4)

    # Estimated ad cost per sale = CPC ÷ conversion rate. If conv rate
    # is 0 we charge 0 (don't divide by zero).
    if payload.ad_conversion_rate > 0:
        ad_cost = round(payload.ad_cpc_usd / payload.ad_conversion_rate, 4)
    else:
        ad_cost = 0.0

    profit = round(
        payload.sale_price_usd - base - marketplace_fee - payload.shipping_usd - ad_cost,
        4,
    )
    margin_pct = round(
        100.0 * profit / payload.sale_price_usd,
        2,
    )

    note: str | None = None
    if base == 0:
        note = "unsupported product_type — using $0 base cost"
    if margin_pct < 0:
        note = (note or "") + ("; " if note else "") + "negative margin — review price or ad spend"

    return ProfitBreakdown(
        sale_price_usd=round(payload.sale_price_usd, 4),
        base_cost_usd=round(base, 4),
        marketplace_fee_usd=marketplace_fee,
        shipping_usd=round(payload.shipping_usd, 4),
        ad_cost_usd=ad_cost,
        profit_usd=profit,
        margin_pct=margin_pct,
        printer=payload.printer,
        note=note,
    )


def supported_product_types() -> list[ProductType]:
    """For populating UI drop-downs."""
    return list(_BASE_COSTS_USD.keys())


def supported_printers() -> list[PrinterId]:
    return ["printful", "printify", "gelato", "customcat", "spod"]
