import asyncio
import os

token = os.environ.get("APIFY_API_TOKEN", "")
print(f"Token: present={bool(token)}, length={len(token)}")

from scalemyprints.infrastructure.niche_apis.apify_etsy import ApifyEtsyAdapter
from scalemyprints.domain.niche.enums import Country

async def test():
    adapter = ApifyEtsyAdapter(api_token=token)
    print("Calling Apify (30-90 seconds)...")
    result = await adapter.fetch("dog mom", Country.US)
    print("--- RESULT ---")
    print(f"  Listing count: {result.listing_count}")
    print(f"  Avg price USD: {result.avg_price_usd}")
    print(f"  Sample size: {result.sample_size}")
    print(f"  Unique sellers est: {result.unique_sellers_estimate}")
    print(f"  Sample URLs: {result.sample_listings_urls[:2]}")
    print(f"  Error: {result.error}")
    print(f"  Duration: {result.duration_ms}ms")

asyncio.run(test())
