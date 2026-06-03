"""Phase 4.8 — `compute()` honors a live base cost override."""

from __future__ import annotations

from scalemyprints.domain.spy import profit_service
from scalemyprints.domain.spy.enums import Marketplace
from scalemyprints.domain.spy.profit_service import ProfitInput


def test_live_base_cost_overrides_static_table() -> None:
    # Static printify t-shirt = $8.45; live = $9.99 should win.
    out = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            printer="printify",
        ),
        live_base_cost_usd=9.99,
    )
    assert out.base_cost_usd == 9.99
    assert out.note and "live printer API" in out.note


def test_zero_or_none_live_quote_falls_back_to_static() -> None:
    static = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            printer="printify",
        )
    )
    none_live = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            printer="printify",
        ),
        live_base_cost_usd=None,
    )
    zero_live = profit_service.compute(
        ProfitInput(
            marketplace=Marketplace.ETSY,
            product_type="t_shirt",
            sale_price_usd=24.99,
            printer="printify",
        ),
        live_base_cost_usd=0.0,
    )
    assert none_live.base_cost_usd == static.base_cost_usd
    assert zero_live.base_cost_usd == static.base_cost_usd
    # The "live printer API" note must NOT appear for fallback paths.
    assert "live printer API" not in (none_live.note or "")
    assert "live printer API" not in (zero_live.note or "")
