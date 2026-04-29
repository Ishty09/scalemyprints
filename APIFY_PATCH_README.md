# Apify Etsy Integration Patch

This patch adds an **Apify-powered Etsy adapter** to bypass Etsy's bot detection
and rate limits. The free Etsy public scraper now becomes a fallback; Apify
becomes the primary marketplace data source when configured.

## Why This Matters

Your previous testing showed:
- **Etsy public scraper**: HTTP 403 (Cloudflare bot detection)
- **Google Trends**: HTTP 429 (shared VPN IPs already rate-limited)
- **VPN didn't help**: shared free-tier IPs already flagged globally

Apify uses **residential proxies** (real home IPs from real ISPs), which Etsy's
bot detection treats as legitimate visitors. This works **even from Bangladesh**
because the proxy is the source IP, not your machine.

## What's in This Patch

### New file
- `apps/workers/src/scalemyprints/infrastructure/niche_apis/apify_etsy.py` — the new adapter

### Modified files
- `apps/workers/src/scalemyprints/infrastructure/niche_apis/__init__.py` — exports `ApifyEtsyAdapter`
- `apps/workers/src/scalemyprints/infrastructure/container.py` — auto-switches when configured

### New tests
- `apps/workers/tests/infrastructure/niche_apis/test_apify_etsy.py` — 58 tests covering parsers, run input shape, and adapter behavior with mocked Apify client

## Apply Instructions (Windows PowerShell)

### Step 1: Extract the patch over your project

```powershell
$projectRoot = "F:\chrome Download\scalemyprints\scalemyprints"
Expand-Archive -Path "$HOME\Downloads\scalemyprints-apify-etsy.zip" -DestinationPath $projectRoot -Force
Write-Host "Patch applied!"
```

### Step 2: Install the apify-client Python library

```powershell
cd "$projectRoot\apps\workers"
uv pip install --system "apify-client>=1.7.0"
```

### Step 3: Update your `.env` file

Open `apps/workers/.env` and confirm these two lines are present:

```bash
NICHE_MARKETPLACE_PROVIDER=apify
APIFY_API_TOKEN=apify_api_<your-rotated-token-here>
```

(The token you pasted in chat earlier — you should have rotated it via
https://console.apify.com/account/integrations and put the new one here.)

### Step 4: Verify all tests still pass

```powershell
cd "$projectRoot\apps\workers"
$env:PYTHONPATH = "src"
python -m pytest tests/ --no-cov -q
```

**Expected:** `393 passed` (335 existing + 58 new)

### Step 5: Restart workers

In your workers terminal, press `Ctrl+C` to stop, then:

```powershell
$env:PYTHONPATH = "src"
uv run uvicorn scalemyprints.main:app --reload --host 0.0.0.0 --port 8000
```

### Step 6: Confirm Apify is wired in startup logs

You should see this line in the workers boot log:

```
service_container_initialized ... niche_marketplace=apify ...
marketplace_provider_apify actor=epctex/etsy-scraper
```

If you see `niche_marketplace=etsy_public` instead, the env var didn't load.
Double-check your `.env` and restart again.

## How the Auto-Switch Works

In `container.py`, the marketplace provider selection follows this logic:

| `NICHE_MARKETPLACE_PROVIDER` | `APIFY_API_TOKEN` | Provider used |
|------------------------------|-------------------|---------------|
| `apify`                       | set              | **Apify** ✅ |
| `apify`                       | empty            | EtsyPublicSearchAdapter (warns) |
| `etsy_public` (default)       | anything         | EtsyPublicSearchAdapter |
| anything else                 | anything         | EtsyPublicSearchAdapter |

Setting `APIFY_API_TOKEN` alone does NOT switch — you must also set
`NICHE_MARKETPLACE_PROVIDER=apify`. This is intentional: it keeps the system
predictable. You can put your token in `.env` for later use without it being
silently activated.

## Cost Awareness

The `epctex/etsy-scraper` actor charges roughly **$0.04–0.05 compute units
per 50 items**. With our settings (`maxItems=30`, single page):

- **One search ≈ $0.025–$0.05**
- **$5 free credit ≈ 100–200 searches**
- **After credit**: ~$0.05/search at current rates

The 6-hour cache in `NicheSearchService` means repeat searches for the same
keyword don't cost anything extra — only fresh keywords incur cost.

If a search fails (Apify run errors, network timeout, etc.), the adapter
returns a `MarketplaceData` with `error=...` set; the search service marks
the niche as `degraded=True` and continues with whatever signals worked. **You
are still charged for failed runs by Apify**, so we keep `maxItems=30` modest
to bound the worst case.

## Testing It

After applying the patch, in your browser:

1. Go to `http://localhost:3000/dashboard/niche-radar`
2. Search for `dog mom` in `US`
3. Watch the workers terminal for these log lines:

```
apify_run_starting    keyword='dog mom' ...
apify_fetch_complete  fetched=30 avg_price=22.50 duration_ms=45000
```

4. The niche result should now show **real listing counts** and **real prices**
   from Etsy — not the 403 errors you were seeing before.

If it still shows `degraded=true`, the Google Trends side might still be
rate-limited (separate issue, not solved by Apify). The static events DB will
still surface the seasonality boost.

## Troubleshooting

### "Marketplace provider type: EtsyPublicSearchAdapter" in startup logs

The env vars didn't load. Check:
- `.env` is in `apps/workers/` (not project root)
- Both `NICHE_MARKETPLACE_PROVIDER=apify` AND `APIFY_API_TOKEN=apify_api_...` are present
- No quotes around values in `.env`
- Restart the workers process completely

### "apify_client_missing" error in logs

You forgot Step 2: `uv pip install --system "apify-client>=1.7.0"`

### "actor_status_FAILED" or "actor_status_TIMED-OUT"

The actor itself failed. Common causes:
- Apify free credit exhausted → check https://console.apify.com/billing
- Rate-limit on Apify side → wait 5 minutes, retry
- Etsy returned an unusual error to the actor → try a different keyword

### Search takes 30–90 seconds

Normal. Apify needs to spin up a browser, load Etsy, scroll, parse. The 6-hour
cache makes repeat searches instant.

### "unexpected:RuntimeError" or similar

Network or API error. The adapter logs the full exception type. Check Apify
console for the run details: https://console.apify.com/actors/runs

## What's Still Pending

This patch fixes Etsy specifically. Other open items from previous sessions:

- **Google Trends rate limits** — separate issue, not addressed here.
  Static events DB compensates for many "what's coming up" use cases.
- **Marker / TMView trademark APIs** — still need US datacenter IP (DigitalOcean
  deploy). Apify is for marketplace scraping, not trademark APIs.
- **Apify token security** — make sure the token you originally pasted in chat
  is rotated. Old token revoked, new token in `.env` only.

## Files Changed Summary

```
+ apps/workers/src/scalemyprints/infrastructure/niche_apis/apify_etsy.py   (293 lines, new)
~ apps/workers/src/scalemyprints/infrastructure/niche_apis/__init__.py     (exports updated)
~ apps/workers/src/scalemyprints/infrastructure/container.py               (auto-switch logic)
+ apps/workers/tests/infrastructure/niche_apis/test_apify_etsy.py          (58 tests, new)
```

**Total: 4 files, 1 new test file with 58 tests, 393/393 tests passing.**
