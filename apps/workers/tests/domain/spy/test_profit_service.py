"""Profit calculator — pure math."""

from __future__ import annotations

import pytest

from scalemyprints.domain.spy import profit_service
from scalemyprints.domain.spy.enums import Marketplace
from scalemyprints.domain.spy.profit_service import ProfitInput


def test_etsy_t_shirt_printify_basic() -> None:
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            printer="printify",
        )
    )
    assert out.base_cost_usd == 8.45
    # Etsy fee: 6.5% + $0.20 listing + 3% processing
    # = 24.99 * 0.065 + 0.20 + 24.99 * 0.03 = 1.62 + 0.20 + 0.75 = ~2.57
    assert 2.55 <= out.marketplace_fee_usd <= 2.60
    assert out.profit_usd > 0
    assert -100 < out.margin_pct < 100


def test_amazon_merch_royalty_share() -> None:
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.AMAZON_MERCH,
            product_type="t_shirt",
            sale_price_usd=19.99,
            printer="printify",  # Amazon Merch model — printer cost is informational
        )
    )
    # Amazon keeps ~76% of sale price (seller gets ~24% royalty)
    # fee = 19.99 * 0.76 = 15.1924
    assert 15.0 <= out.marketplace_fee_usd <= 15.3


def test_redbubble_artist_margin() -> None:
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.REDBUBBLE,
            product_type="t_shirt",
            sale_price_usd=25.00,
            printer="printify",
        )
    )
    # Redbubble keeps 80%; artist gets 20% margin
    # fee = 25 * 0.80 = 20.00
    assert out.marketplace_fee_usd == 20.0


def test_ad_cost_uses_cpc_over_conv_rate() -> None:
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            ad_cpc_usd=0.50,
            ad_conversion_rate=0.05,
        )
    )
    # ad_cost = 0.50 / 0.05 = $10 per sale
    assert out.ad_cost_usd == 10.0


def test_negative_margin_flagged_in_note() -> None:
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="hoodie",     # base ~$22-30
            sale_price_usd=15.00,      # selling at a loss
            printer="printify",
        )
    )
    assert out.profit_usd < 0
    assert out.note and "negative margin" in out.note


def test_supported_lists_exposed() -> None:
    types = profit_service.supported_product_types()
    assert "t_shirt" in types
    assert "mug_11oz" in types
    printers = profit_service.supported_printers()
    assert "printful" in printers
    assert "printify" in printers


def test_shipping_subtracted() -> None:
    a = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            shipping_usd=0.0,
        )
    )
    b = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            shipping_usd=4.95,
        )
    )
    assert abs((a.profit_usd - b.profit_usd) - 4.95) < 0.01


def test_invalid_product_type_rejected_at_boundary() -> None:
    # ProductType is Literal — Pydantic rejects unknown values at the
    # model boundary, so the "fall back to 0" path is unreachable in
    # practice. Document the contract: the model validator throws.
    import pytest as _pt
    with _pt.raises(Exception):
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="unicorn_widget",  # type: ignore[arg-type]
            sale_price_usd=10.00,
        )
