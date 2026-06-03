"""Parser-only tests for the Phase 4.7 marketplaces.

We don't hit the network — instead we feed each parser the kind of
HTML snippet we expect the real site to embed.
"""

from __future__ import annotations

import json

from scalemyprints.domain.spy.enums import Marketplace
from scalemyprints.infrastructure.spy_apis.society6_spy import (
    _parse_search as parse_society6,
)
from scalemyprints.infrastructure.spy_apis.teepublic_spy import (
    _parse_search as parse_teepublic,
)
from scalemyprints.infrastructure.spy_apis.zazzle_spy import (
    _parse_search as parse_zazzle,
)


# -----------------------------------------------------------------------------
# Teepublic
# -----------------------------------------------------------------------------


def test_teepublic_parses_apollo_state_designs() -> None:
    apollo = {
        "Design:12345": {
            "id": 12345,
            "title": "Cool vintage motorcycle design",
            "slug": "cool-vintage-motorcycle",
            "imageUrl": "https://cdn.teepublic.com/12345.jpg",
            "price": 22.0,
            "user": {"username": "rider99"},
        },
        "Design:67890": {
            "id": 67890,
            "title": "Cat astronaut",
            "slug": "cat-astronaut",
            "squareImageUrl": "https://cdn.teepublic.com/67890.jpg",
            "price": 24.0,
        },
        # decoy
        "Tag:42": {"id": 42, "label": "vintage"},
    }
    html = f"<html>window.__APOLLO_STATE__ = {json.dumps(apollo)};</html>"
    listings = parse_teepublic(html, limit=10)
    assert len(listings) == 2
    by_id = {l.external_id: l for l in listings}
    assert "12345" in by_id
    assert by_id["12345"].marketplace == Marketplace.TEEPUBLIC
    assert by_id["12345"].shop_handle == "rider99"
    assert by_id["67890"].title == "Cat astronaut"


def test_teepublic_returns_empty_on_no_state() -> None:
    assert parse_teepublic("<html>nothing here</html>", limit=10) == []


# -----------------------------------------------------------------------------
# Society6
# -----------------------------------------------------------------------------


def test_society6_walks_initial_state_for_artworks() -> None:
    state = {
        "page": {
            "results": [
                {
                    "id": "abc-001",
                    "title": "Mountain sunrise print",
                    "previewImageUrl": "https://society6.com/abc-001.jpg",
                    "price": 28,
                    "artist": {"username": "sunny"},
                },
                {
                    "id": "abc-002",
                    "title": "Coastal map watercolor",
                    "imageUrl": "https://society6.com/abc-002.jpg",
                    "price": 32,
                },
            ]
        }
    }
    html = f"<html>window.__INITIAL_STATE__ = {json.dumps(state)};</html>"
    listings = parse_society6(html, limit=10)
    assert len(listings) == 2
    by_id = {l.external_id: l for l in listings}
    assert by_id["abc-001"].marketplace == Marketplace.SOCIETY6
    assert by_id["abc-001"].shop_handle == "sunny"
    assert by_id["abc-002"].title == "Coastal map watercolor"


def test_society6_respects_limit() -> None:
    state = {
        "results": [
            {
                "id": f"id-{i}",
                "title": f"thing {i}",
                "previewImageUrl": f"https://society6.com/{i}.jpg",
            }
            for i in range(15)
        ]
    }
    html = f"<html>window.__INITIAL_STATE__ = {json.dumps(state)};</html>"
    listings = parse_society6(html, limit=5)
    assert len(listings) == 5


# -----------------------------------------------------------------------------
# Zazzle
# -----------------------------------------------------------------------------


def test_zazzle_walks_next_data_for_products() -> None:
    data = {
        "props": {
            "pageProps": {
                "products": [
                    {
                        "productId": "256ab",
                        "title": "Funny dad joke mug",
                        "imageUrl": "https://zazzle.com/256ab.jpg",
                        "price": 19.95,
                        "storeName": "dadjokes",
                    },
                    {
                        "id": "789cd",
                        "name": "Wedding invitation suite",
                        "imagePath": "https://zazzle.com/789cd.jpg",
                        "listPrice": {"amount": 35.5},
                    },
                ]
            }
        }
    }
    html = (
        '<script id="__NEXT_DATA__" type="application/json">'
        + json.dumps(data)
        + "</script>"
    )
    listings = parse_zazzle(html, limit=10)
    assert len(listings) == 2
    by_id = {l.external_id: l for l in listings}
    assert by_id["256ab"].marketplace == Marketplace.ZAZZLE
    assert by_id["256ab"].shop_handle == "dadjokes"
    assert by_id["789cd"].price_usd == 35.5


def test_zazzle_empty_on_missing_next_data() -> None:
    assert parse_zazzle("<html>no next data</html>", limit=10) == []
