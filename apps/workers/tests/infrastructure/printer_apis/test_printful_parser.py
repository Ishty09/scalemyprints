"""Pure-parser tests for the Printful adapter — no network."""

from __future__ import annotations

from scalemyprints.infrastructure.printer_apis.printful import _pick_cheapest


def test_picks_cheapest_variant_across_products() -> None:
    catalog = {
        "result": [
            {
                "title": "Unisex Cotton Tee",
                "variants": [
                    {"price": "11.95"},
                    {"price": "12.95"},
                ],
            },
            {
                "title": "Bella+Canvas Long-Sleeve",
                "variants": [
                    {"price": "17.95"},
                ],
            },
        ]
    }
    assert _pick_cheapest(catalog, ("unisex",)) == 11.95


def test_keyword_filter_skips_non_matching_products() -> None:
    catalog = {
        "result": [
            {"title": "Hoodie", "variants": [{"price": 8.00}]},
            {"title": "Unisex Tee", "variants": [{"price": 12.95}]},
        ]
    }
    # If we only want hoodies, the tee shouldn't pull the price down
    assert _pick_cheapest(catalog, ("hoodie",)) == 8.00


def test_ignores_non_numeric_and_zero_prices() -> None:
    catalog = {
        "result": [
            {
                "title": "Anything",
                "variants": [
                    {"price": "0"},
                    {"price": "not-a-number"},
                    {"price": "9.99"},
                ],
            }
        ]
    }
    assert _pick_cheapest(catalog, ()) == 9.99


def test_handles_empty_catalog() -> None:
    assert _pick_cheapest({}, ()) is None
    assert _pick_cheapest({"result": []}, ()) is None
    assert _pick_cheapest([], ()) is None


def test_falls_through_to_base_price_or_retail_price() -> None:
    catalog = [
        {
            "title": "Product",
            "variants": [{"retail_price": "15.50"}],
        },
        {
            "title": "Product B",
            "variants": [{"base_price": "11.10"}],
        },
    ]
    assert _pick_cheapest(catalog, ()) == 11.10
