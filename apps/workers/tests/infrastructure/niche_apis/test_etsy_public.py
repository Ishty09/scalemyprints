"""Tests for Etsy public adapter — HTML parsing helpers."""

from __future__ import annotations

import pytest

from scalemyprints.infrastructure.niche_apis.etsy_public import (
    _extract_listing_count,
    _extract_listing_urls,
    _extract_prices,
    _parse_etsy_html,
)


class TestExtractListingCount:
    def test_data_attribute_pattern(self):
        html = '<div data-search-count="12345" class="x">'
        assert _extract_listing_count(html) == 12345

    def test_results_for_text_pattern(self):
        html = '<span>2,547 results for "dog mom"</span>'
        assert _extract_listing_count(html) == 2547

    def test_json_pattern(self):
        html = '{"listingResultsCount": 8901, "other": true}'
        assert _extract_listing_count(html) == 8901

    def test_no_match_returns_none(self):
        assert _extract_listing_count("no relevant content here") is None

    def test_handles_commas_in_count(self):
        html = '<span>15,234 results for foo</span>'
        assert _extract_listing_count(html) == 15234


class TestExtractListingUrls:
    def test_extracts_listing_links(self):
        html = '''
        <a href="https://www.etsy.com/listing/12345/cool-shirt">Shirt</a>
        <a href="https://www.etsy.com/listing/67890/funny-mug">Mug</a>
        '''
        urls = _extract_listing_urls(html)
        assert len(urls) == 2
        assert "https://www.etsy.com/listing/12345/cool-shirt" in urls

    def test_dedupes_urls(self):
        html = '''
        <a href="https://www.etsy.com/listing/12345/x">a</a>
        <a href="https://www.etsy.com/listing/12345/x">b</a>
        '''
        urls = _extract_listing_urls(html)
        assert len(urls) == 1

    def test_caps_at_20(self):
        html = "".join(
            f'<a href="https://www.etsy.com/listing/{i}/x">link</a>'
            for i in range(50)
        )
        urls = _extract_listing_urls(html)
        assert len(urls) == 20

    def test_ignores_non_listing_links(self):
        html = '''
        <a href="https://www.etsy.com/shop/foo">shop</a>
        <a href="https://www.etsy.com/listing/123/x">listing</a>
        '''
        urls = _extract_listing_urls(html)
        assert len(urls) == 1

    def test_strips_query_strings(self):
        html = '<a href="https://www.etsy.com/listing/12345/x?utm=source">x</a>'
        urls = _extract_listing_urls(html)
        assert len(urls) == 1
        assert "?" not in urls[0]


class TestExtractPrices:
    def test_extracts_dollar_prices(self):
        html = '<span>Price: $24.99</span> <span>$12.50</span>'
        prices = _extract_prices(html)
        assert 24.99 in prices
        assert 12.50 in prices

    def test_filters_outliers_over_200(self):
        html = '<span>$24.99</span> <span>$5000.00</span>'
        prices = _extract_prices(html)
        assert 24.99 in prices
        assert 5000.0 not in prices

    def test_filters_outliers_under_1(self):
        html = '<span>$0.50</span> <span>$24.99</span>'
        prices = _extract_prices(html)
        assert 0.50 not in prices

    def test_caps_at_30_samples(self):
        html = " ".join(f"$10.{i:02d}" for i in range(100))
        prices = _extract_prices(html)
        assert len(prices) <= 30

    def test_no_prices_returns_empty(self):
        prices = _extract_prices("no prices here")
        assert prices == []


class TestParseEtsyHtml:
    def test_full_parse(self):
        html = '''
        <div data-search-count="500">
        <a href="https://www.etsy.com/listing/1/dog">Dog Mom</a>
        <a href="https://www.etsy.com/listing/2/cat">Cat Mom</a>
        <span>$24.99</span>
        <span>$19.95</span>
        '''
        parsed = _parse_etsy_html(html)
        assert parsed["listing_count"] == 500
        assert len(parsed["sample_urls"]) == 2
        assert parsed["avg_price"] is not None
        assert parsed["sample_size"] == 2

    def test_unique_sellers_estimate_for_small_listing(self):
        html = '<div data-search-count="30">'
        parsed = _parse_etsy_html(html)
        # <50 listings → 1:1 ratio
        assert parsed["unique_sellers_estimate"] == 30

    def test_unique_sellers_estimate_for_medium_listing(self):
        html = '<div data-search-count="500">'
        parsed = _parse_etsy_html(html)
        # 50-1000 → 75% ratio
        assert parsed["unique_sellers_estimate"] == 375

    def test_unique_sellers_estimate_for_large_listing(self):
        html = '<div data-search-count="5000">'
        parsed = _parse_etsy_html(html)
        # >1000 → 50% ratio
        assert parsed["unique_sellers_estimate"] == 2500

    def test_no_listings_no_seller_estimate(self):
        html = "<div>nothing here</div>"
        parsed = _parse_etsy_html(html)
        assert parsed["listing_count"] is None
        assert parsed["unique_sellers_estimate"] is None
