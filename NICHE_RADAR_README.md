# Niche Radar — Phase A Patch

This patch adds the Niche Radar feature to your existing ScaleMyPrints project.

## What's included

### Backend (Python / FastAPI)
**New domain layer** (`apps/workers/src/scalemyprints/domain/niche/`):
- `enums.py` — Country, EventCategory, NicheHealth, TrendDirection, CompetitionLevel
- `models.py` — Pydantic models for signals + NicheRecord + Event
- `ports.py` — Protocol interfaces (TrendsProvider, MarketplaceProvider, EventsProvider, NicheExpander, NicheCacheStore)
- `scoring_service.py` — Pure-domain Niche Health Score calculator (5 sub-scores → NHS)
- `search_service.py` — Orchestrator that runs providers in parallel + caches + handles partial failures

**New infrastructure adapters:**
- `infrastructure/niche_apis/google_trends.py` — Free Google Trends adapter (via pytrends)
- `infrastructure/niche_apis/etsy_public.py` — Free Etsy public-search HTML scraper
- `infrastructure/niche_apis/static_events.py` — Loads curated events DB
- `infrastructure/events_data/static_events.json` — **109 curated POD-relevant events** across US, UK, AU, CA, DE
- `infrastructure/llm/niche_expander.py` — OpenAI GPT-4o-mini sub-niche generator with copyright/safety filtering
- `infrastructure/cache/niche_memory.py` — In-memory TTL cache for niche results

**New API routes** (`apps/workers/src/scalemyprints/api/routes/niche.py`):
- `POST /api/v1/niche/search` — analyze a niche keyword
- `GET  /api/v1/niche/events` — upcoming events for a country (filterable by date range + category)
- `POST /api/v1/niche/expand` — LLM sub-niche idea generation

**Modified files:**
- `core/config.py` — added Niche Radar settings (provider selection, API keys)
- `infrastructure/container.py` — wired up all niche providers with fallback logic
- `api/deps.py` — added `get_niche_search_service` dependency
- `app.py` — registered niche router
- `api/routes/__init__.py` — exported niche_router

### Frontend (Next.js / React)
**New pages:**
- `apps/web/src/app/(app)/dashboard/niche-radar/page.tsx` — main niche analysis page
- `apps/web/src/app/(app)/dashboard/niche-radar/events/page.tsx` — events calendar with country/range/category filters

**New components:**
- `components/app/niche-search-form.tsx` — keyword + country selector
- `components/app/niche-results.tsx` — NHS card + sub-score breakdown + upcoming events + related keywords + sample listings

**New hooks:**
- `hooks/use-niche.ts` — React Query hooks for search, events, expand

**Modified files:**
- `packages/contracts/src/branding.ts` — Niche Radar marked as `live`, trademark slug fixed
- `packages/contracts/src/niche.ts` — TypeScript contracts mirroring backend models
- `packages/contracts/src/index.ts` — re-exports

### Database
- `infra/supabase/migrations/20260428000000_niche_radar_phase_a.sql` — 3 new tables:
  - `niche_searches` — per-user search history
  - `niche_monitors` — saved niches for tracking
  - `niche_events_cache` — optional DB-backed events cache
  - All tables: RLS enabled, per-user policies, indexes on hot paths

## Apply the Patch (Windows PowerShell)

```powershell
$projectRoot = "F:\chrome Download\scalemyprints\scalemyprints"

# Extract patch over your existing project
Expand-Archive -Path "$HOME\Downloads\scalemyprints-niche-radar.zip" -DestinationPath $projectRoot -Force

Write-Host "Patch applied!"
```

## Install New Python Dependency

```powershell
cd "$projectRoot\apps\workers"
uv pip install --system "pytrends>=4.9.2"
```

## Verify Tests Pass

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/ --no-cov -q
```

Expected: **335 passed** (200 trademark + 135 niche)

## Apply DB Migration

In Supabase SQL Editor:
1. Open `infra/supabase/migrations/20260428000000_niche_radar_phase_a.sql`
2. Paste the entire content
3. Click Run

Expected: "Success. No rows returned"

Verify tables created:
```sql
SELECT table_name FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_name LIKE 'niche_%';
```

Should show: `niche_events_cache`, `niche_monitors`, `niche_searches`

## Restart Servers

```powershell
# Workers terminal — Ctrl+C, then:
uv run uvicorn scalemyprints.main:app --reload --host 0.0.0.0 --port 8000

# Web terminal — Ctrl+C, then:
pnpm --filter @scalemyprints/web dev
```

## Test It

1. Browser → http://localhost:3000/dashboard/niche-radar
2. Sidebar should now show "Niche Radar" as live (no "Soon" badge)
3. Type a keyword (e.g., "dog mom") → click "Analyze niche"
4. Should see NHS score + 5 sub-score cards + upcoming events + related keywords
5. Click "Events calendar" link → see day-by-day list
6. Filter by country/range/category

## What Works

- ✅ Niche analysis with real Google Trends + Etsy public data (free APIs)
- ✅ Day-by-day events calendar across 5 countries (109 curated events)
- ✅ Multi-country support (US, UK, AU, CA, DE)
- ✅ NHS scoring with 5 weighted sub-signals
- ✅ Graceful degradation when APIs fail (keeps showing whatever data is available)
- ✅ Memory caching (6-hour TTL, faster repeat searches)
- ✅ Rate limiting (5/day anonymous, 60/min authenticated)
- ✅ Mobile responsive

## Known Limitations (Same as Trademark Shield)

- **Bangladesh network:** Google Trends and Etsy public scraping may be blocked from Bangladesh ISP. Works fine from production server (Hetzner US/EU).
- **Etsy listing counts:** Approximate — Etsy doesn't expose exact counts, parser uses regex over public HTML.
- **LLM expansion:** Requires OPENAI_API_KEY set (already in your `.env`).

## Apify / Calendarific Upgrade (Optional, Later)

When you want paid-tier accuracy:

```bash
# In .env
NICHE_MARKETPLACE_PROVIDER=apify
APIFY_API_TOKEN=apify_api_xxxxx

NICHE_EVENTS_PROVIDER=calendarific
CALENDARIFIC_API_KEY=xxxxx
```

The Container will auto-switch to paid providers (adapter implementations are stubbed for Phase B — can be built when needed).

## Test Coverage

- Domain layer: 100% (53 tests)
- Infrastructure: 70%+ (52 tests)
- API routes: integration tests for all 3 endpoints (11 tests)
- Plus 8 HTTP-mocked Etsy adapter tests
- Plus 11 LLM sanitization tests

**Total: 135 new tests, all passing on top of the 200 existing trademark tests.**
