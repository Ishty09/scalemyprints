"""Tests for Apify Etsy adapter — parser logic + mocked actor calls."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scalemyprints.domain.niche.enums import Country
from scalemyprints.infrastructure.niche_apis.apify_etsy import (
    ApifyEtsyAdapter,
    _estimate_unique_sellers,
    _extract_listing_age_days,
    _extract_price,
    _extract_seller,
    _extract_total_results,
    _extract_urls,
    _parse_apify_items,
)


# =============================================================================
# Construction & validation
# =============================================================================


class TestApifyEtsyAdapterConstruction:
    def test_requires_api_token(self):
        with pytest.raises(ValueError, match="api_token"):
            ApifyEtsyAdapter(api_token="")

    def test_default_actor_id(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        assert adapter._actor_id == "epctex/etsy-scraper"

    def test_custom_actor_id(self):
        adapter = ApifyEtsyAdapter(api_token="t", actor_id="other/scraper")
        assert adapter._actor_id == "other/scraper"

    def test_default_max_items(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        assert adapter._max_items == 30


# =============================================================================
# Run input shape
# =============================================================================


class TestRunInput:
    def test_input_includes_search_keyword(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("dog mom", Country.US)
        assert run_input["search"] == "dog mom"

    def test_input_includes_max_items(self):
        adapter = ApifyEtsyAdapter(api_token="t", max_items_per_search=15)
        run_input = adapter._build_run_input("test", Country.US)
        assert run_input["maxItems"] == 15

    def test_input_includes_apify_proxy(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("test", Country.US)
        assert run_input["proxy"] == {"useApifyProxy": True}

    def test_input_disables_descriptions_for_cost(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("test", Country.US)
        assert run_input["includeDescription"] is False

    def test_country_uk_uses_gb_ship_to(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("test", Country.UK)
        assert "ship_to=GB" in run_input["startUrls"][0]

    def test_country_au_ship_to(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("test", Country.AU)
        assert "ship_to=AU" in run_input["startUrls"][0]

    def test_keyword_with_spaces_url_encoded(self):
        adapter = ApifyEtsyAdapter(api_token="t")
        run_input = adapter._build_run_input("dog mom", Country.US)
        # Spaces encoded as +
        assert "q=dog+mom" in run_input["startUrls"][0]


# =============================================================================
# Price extraction (multiple shapes)
# =============================================================================


class TestExtractPrice:
    def test_numeric_price(self):
        assert _extract_price({"price": 24.99}) == 24.99

    def test_string_price(self):
        assert _extract_price({"price": "24.99"}) == 24.99

    def test_string_price_with_dollar_sign(self):
        assert _extract_price({"price": "$24.99"}) == 24.99

    def test_dict_price_usd(self):
        item = {"price": {"amount": "29.95", "currencyCode": "USD"}}
        assert _extract_price(item) == 29.95

    def test_dict_price_non_usd_skipped(self):
        item = {"price": {"amount": "29.95", "currencyCode": "EUR"}}
        assert _extract_price(item) is None

    def test_outlier_too_high_skipped(self):
        assert _extract_price({"price": 5000.0}) is None

    def test_outlier_too_low_skipped(self):
        assert _extract_price({"price": 0.5}) is None

    def test_missing_price(self):
        assert _extract_price({}) is None

    def test_invalid_string(self):
        assert _extract_price({"price": "not-a-number"}) is None

    def test_dict_with_value_field(self):
        item = {"price": {"value": 19.99, "currency": "USD"}}
        assert _extract_price(item) == 19.99


# =============================================================================
# Seller extraction
# =============================================================================


class TestExtractSeller:
    def test_string_seller(self):
        assert _extract_seller({"shop": "CoolShop"}) == "CoolShop"

    def test_dict_seller(self):
        assert _extract_seller({"shop": {"name": "CoolShop"}}) == "CoolShop"

    def test_seller_field_name(self):
        assert _extract_seller({"seller": "OtherShop"}) == "OtherShop"

    def test_dict_with_shop_name_field(self):
        item = {"shop": {"shopName": "ThisShop"}}
        assert _extract_seller(item) == "ThisShop"

    def test_missing_seller(self):
        assert _extract_seller({}) is None

    def test_empty_string_seller(self):
        assert _extract_seller({"shop": ""}) is None

    def test_strips_whitespace(self):
        assert _extract_seller({"shop": "  Shop  "}) == "Shop"


# =============================================================================
# URL extraction & dedup
# =============================================================================


class TestExtractUrls:
    def test_valid_etsy_url(self):
        items = [{"url": "https://www.etsy.com/listing/12345/dog-mom-shirt"}]
        urls = _extract_urls(items)
        assert urls == ["https://www.etsy.com/listing/12345/dog-mom-shirt"]

    def test_strips_query_string(self):
        items = [{"url": "https://www.etsy.com/listing/12345/x?utm=source"}]
        urls = _extract_urls(items)
        assert urls == ["https://www.etsy.com/listing/12345/x"]

    def test_dedupes_after_query_strip(self):
        items = [
            {"url": "https://www.etsy.com/listing/12345/x?ref=a"},
            {"url": "https://www.etsy.com/listing/12345/x?ref=b"},
        ]
        urls = _extract_urls(items)
        assert len(urls) == 1

    def test_alternate_field_names(self):
        items = [
            {"listingUrl": "https://www.etsy.com/listing/1/a"},
            {"link": "https://www.etsy.com/listing/2/b"},
        ]
        urls = _extract_urls(items)
        assert len(urls) == 2

    def test_non_listing_urls_filtered(self):
        items = [
            {"url": "https://www.etsy.com/shop/some-shop"},
            {"url": "https://www.etsy.com/listing/1/a"},
        ]
        urls = _extract_urls(items)
        assert len(urls) == 1


# =============================================================================
# Total results extraction
# =============================================================================


class TestExtractTotalResults:
    def test_int_total(self):
        items = [{"totalResults": 5234}]
        assert _extract_total_results(items) == 5234

    def test_string_total(self):
        items = [{"totalResults": "1234"}]
        assert _extract_total_results(items) == 1234

    def test_snake_case_field(self):
        items = [{"total_results": 999}]
        assert _extract_total_results(items) == 999

    def test_missing_returns_none(self):
        items = [{"title": "no count"}]
        assert _extract_total_results(items) is None

    def test_finds_in_later_item(self):
        items = [{"title": "x"}, {"title": "y"}, {"totalResults": 100}]
        assert _extract_total_results(items) == 100

    def test_zero_treated_as_missing(self):
        items = [{"totalResults": 0}]
        assert _extract_total_results(items) is None


# =============================================================================
# Listing age extraction
# =============================================================================


class TestExtractListingAge:
    def test_listing_age_days(self):
        assert _extract_listing_age_days({"listingAgeDays": 120}) == 120

    def test_alternate_age_field(self):
        assert _extract_listing_age_days({"ageDays": 365}) == 365

    def test_snake_case(self):
        assert _extract_listing_age_days({"listing_age_days": 30}) == 30

    def test_negative_value_returns_none(self):
        assert _extract_listing_age_days({"listingAgeDays": -1}) is None

    def test_missing_returns_none(self):
        assert _extract_listing_age_days({}) is None


# =============================================================================
# Unique sellers estimator
# =============================================================================


class TestEstimateUniqueSellers:
    def test_proportional_estimate(self):
        # 30 listings sample, 20 unique sellers, total 1000 → ~666 unique
        result = _estimate_unique_sellers(
            observed_sellers=20, sample_size=30, total_listings=1000
        )
        assert result == 666

    def test_caps_at_total_listings(self):
        # Can't have more sellers than listings
        result = _estimate_unique_sellers(
            observed_sellers=30, sample_size=30, total_listings=100
        )
        assert result == 100

    def test_zero_sellers_returns_none(self):
        result = _estimate_unique_sellers(
            observed_sellers=0, sample_size=30, total_listings=100
        )
        assert result is None

    def test_no_listings_returns_none(self):
        result = _estimate_unique_sellers(
            observed_sellers=10, sample_size=30, total_listings=None
        )
        assert result is None


# =============================================================================
# Full _parse_apify_items integration
# =============================================================================


class TestParseApifyItems:
    def test_empty_items_returns_safe_defaults(self):
        result = _parse_apify_items([])
        assert result["listing_count"] is None
        assert result["avg_price"] is None
        assert result["sample_urls"] == []
        assert result["sample_size"] == 0

    def test_full_realistic_parse(self):
        items = [
            {
                "url": "https://www.etsy.com/listing/1/dog-mom-shirt",
                "title": "Dog Mom Shirt",
                "price": {"amount": "24.99", "currencyCode": "USD"},
                "shop": {"name": "ShopA"},
                "totalResults": 5000,
            },
            {
                "url": "https://www.etsy.com/listing/2/cat-mom-mug",
                "title": "Cat Mom Mug",
                "price": "19.95",
                "shop": "ShopB",
            },
            {
                "url": "https://www.etsy.com/listing/3/another",
                "title": "Another",
                "price": 22.50,
                "shop": {"name": "ShopA"},  # repeat seller
            },
        ]
        result = _parse_apify_items(items)
        assert result["listing_count"] == 5000
        assert result["sample_size"] == 3
        assert result["avg_price"] == round((24.99 + 19.95 + 22.50) / 3, 2)
        assert len(result["sample_urls"]) == 3
        # 2 unique sellers in 3 items, scaled to 5000 → ~3333
        assert result["unique_sellers_estimate"] is not None
        assert 3000 < result["unique_sellers_estimate"] <= 5000

    def test_falls_back_to_sample_size_when_no_total(self):
        items = [
            {"url": "https://www.etsy.com/listing/1/x", "price": 10.0, "shop": "A"}
        ]
        result = _parse_apify_items(items)
        # No totalResults, fallback to sample size
        assert result["listing_count"] == 1

    def test_caps_sample_urls_at_5(self):
        items = [
            {"url": f"https://www.etsy.com/listing/{i}/x", "price": 10.0}
            for i in range(20)
        ]
        result = _parse_apify_items(items)
        assert len(result["sample_urls"]) == 5

    def test_avg_listing_age_when_present(self):
        items = [
            {"url": "https://www.etsy.com/listing/1/x", "listingAgeDays": 100},
            {"url": "https://www.etsy.com/listing/2/x", "listingAgeDays": 200},
        ]
        result = _parse_apify_items(items)
        assert result["avg_listing_age_days"] == 150.0


# =============================================================================
# Adapter behavior with mocked Apify client
# =============================================================================


class TestApifyAdapterWithMockedClient:
    @pytest.mark.asyncio
    async def test_succeeded_run_returns_data(self):
        # Mock the apify_client module
        fake_run = {"status": "SUCCEEDED", "defaultDatasetId": "ds_123"}
        fake_items = [
            {
                "url": "https://www.etsy.com/listing/1/dog-mom",
                "price": "24.99",
                "shop": "CoolShop",
                "totalResults": 1500,
            },
        ]

        async def _fake_iterate_items(**kwargs):
            for item in fake_items:
                yield item

        # Build a chain of mocks: client.actor(id).call() and client.dataset(id).iterate_items()
        actor_mock = MagicMock()
        actor_mock.call = AsyncMock(return_value=fake_run)

        dataset_mock = MagicMock()
        dataset_mock.iterate_items = _fake_iterate_items

        client_mock = MagicMock()
        client_mock.actor = MagicMock(return_value=actor_mock)
        client_mock.dataset = MagicMock(return_value=dataset_mock)

        with patch(
            "apify_client.ApifyClientAsync", return_value=client_mock
        ):
            adapter = ApifyEtsyAdapter(api_token="test_token")
            result = await adapter.fetch("dog mom", Country.US)

        assert result.error is None
        assert result.listing_count == 1500
        assert result.avg_price_usd == 24.99
        assert result.sample_size == 1

    @pytest.mark.asyncio
    async def test_failed_run_returns_error(self):
        fake_run = {"status": "FAILED", "defaultDatasetId": None}

        actor_mock = MagicMock()
        actor_mock.call = AsyncMock(return_value=fake_run)

        client_mock = MagicMock()
        client_mock.actor = MagicMock(return_value=actor_mock)

        with patch("apify_client.ApifyClientAsync", return_value=client_mock):
            adapter = ApifyEtsyAdapter(api_token="test_token")
            result = await adapter.fetch("dog mom", Country.US)

        assert result.error == "actor_status_FAILED"
        assert result.listing_count is None

    @pytest.mark.asyncio
    async def test_call_returns_none_returns_error(self):
        actor_mock = MagicMock()
        actor_mock.call = AsyncMock(return_value=None)

        client_mock = MagicMock()
        client_mock.actor = MagicMock(return_value=actor_mock)

        with patch("apify_client.ApifyClientAsync", return_value=client_mock):
            adapter = ApifyEtsyAdapter(api_token="test_token")
            result = await adapter.fetch("dog mom", Country.US)

        assert result.error == "apify_run_failed"

    @pytest.mark.asyncio
    async def test_unexpected_exception_caught(self):
        actor_mock = MagicMock()
        actor_mock.call = AsyncMock(side_effect=RuntimeError("network died"))

        client_mock = MagicMock()
        client_mock.actor = MagicMock(return_value=actor_mock)

        with patch("apify_client.ApifyClientAsync", return_value=client_mock):
            adapter = ApifyEtsyAdapter(api_token="test_token")
            result = await adapter.fetch("dog mom", Country.US)

        assert result.error is not None
        assert result.error.startswith("unexpected:RuntimeError")
        assert result.listing_count is None

    @pytest.mark.asyncio
    async def test_missing_apify_client_lib(self):
        # Simulate apify-client not installed
        with patch.dict(
            "sys.modules", {"apify_client": None}
        ):
            adapter = ApifyEtsyAdapter(api_token="test_token")
            # Force the import inside fetch() to fail
            import builtins
            real_import = builtins.__import__

            def fail_import(name, *args, **kwargs):
                if name == "apify_client":
                    raise ImportError("no module")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=fail_import):
                result = await adapter.fetch("dog mom", Country.US)

        assert result.error == "apify_client_missing"
