# ScaleMyPrints — CLAUDE.md

AI workforce for Print-on-Demand (POD) sellers. Trademark risk checking + niche/trend discovery.

---

## Monorepo layout

```
scalemyprints/
├── apps/
│   ├── web/          # Next.js 14 (App Router) — deployed via OpenNext → Cloudflare Workers
│   ├── workers/      # Python 3.11 FastAPI backend — trademark + niche search
│   └── extension/    # Chrome extension (Vite + React)
└── packages/
    ├── contracts/    # Shared TS types, Zod schemas, BRAND constants, DB types
    ├── ui/           # Shared React components (shadcn-style)
    ├── utils/        # Shared TS utilities
    └── config/       # Shared eslint / prettier / tailwind / tsconfig presets
```

Package manager: **pnpm 8** with workspaces. Build orchestration: **Turborepo**.

---

## TypeScript / Next.js (apps/web)

**Stack**: Next.js 14 App Router · TypeScript 5 · Tailwind CSS 3 · Supabase (auth + DB) · TanStack Query · Zod · Sonner toasts · Lucide icons

**Route groups**:
- `(app)/` — authenticated dashboard: `dashboard/`, `trademark/`, `niche-radar/`, `settings/`
- `(auth)/` — `login/`, `signup/`
- `(marketing)/` — landing page, `about/`, `pricing/`, `contact/`, `trademark-shield/`
- `api/` — Next.js API routes (thin proxies to Python workers)

**Deployment**: OpenNext Cloudflare adapter (`open-next.config.ts`, `wrangler.jsonc`). `next build` → `wrangler deploy`.

**Dev**: `pnpm dev:web` (port 3000)

**Key conventions**:
- Server components by default; add `'use client'` only when needed
- Supabase client lives in `src/lib/supabase/`
- Data fetching via TanStack Query in client components; `src/lib/api-client.ts` wraps fetch
- All shared types imported from `@scalemyprints/contracts`
- Linting: ESLint + Prettier (via `@scalemyprints/config`); run `pnpm lint:fix`
- Tests: Vitest + Testing Library

---

## Python FastAPI (apps/workers)

**Stack**: Python 3.11 · FastAPI · Pydantic v2 · httpx (async HTTP) · Tenacity (retry) · Supabase · OpenAI · Structlog · Sentry

**Package manager**: `uv` (not pip/poetry). Dev: `pnpm dev:workers` or `uv run uvicorn scalemyprints.main:app --reload --port 8000`. Tests: `pnpm test:workers` or `uv run pytest`.

**Architecture — ports and adapters**:
```
domain/         ← pure business logic, Pydantic models, Protocol interfaces (ports)
infrastructure/ ← concrete adapters: HTTP clients, cache, DB, LLM
api/            ← FastAPI routes, schemas, middleware (thin layer)
core/           ← config (pydantic-settings), logging, DI container
```

**DI / provider selection**: `infrastructure/container.py` is the single wiring point. All infrastructure decisions (which trademark API, which cache, which LLM) happen there based on `Settings`. No other code knows which concrete adapter is in use.

**Trademark adapters** (`infrastructure/trademark_apis/`):

| File | Registry | Default? |
|---|---|---|
| `marker.py` | US via Marker API | Yes (no key needed) |
| `uspto.py` | US via USPTO Open Data | When `US_TRADEMARK_PROVIDER=uspto` + key |
| `tmview.py` | EU via WIPO/EUIPO TMview | Yes (`EU_TRADEMARK_PROVIDER=tmview`) |
| `euipo.py` | EU via EUIPO direct | Legacy, `EU_TRADEMARK_PROVIDER=euipo` |
| `ukipo.py` | UK via UKIPO scrape | Only UK option — **currently 403s from cloud IPs** |
| `ipau.py` | AU via ATMOSS | Only AU option |
| `base.py` | — | Shared HTTP factory + retry (tenacity) + timing |
| `normalizers.py` | — | Domain model normalization |

**Provider pattern** (for US/EU, blueprint for UK): two vars in Settings — one for provider name, one for API key. Container selects at startup; rest of codebase uses the `TrademarkAPI` protocol.

**Key conventions**:
- Linting: Ruff (`ruff check --fix && ruff format`). Config in `pyproject.toml`.
- Type checking: mypy strict. Run: `uv run mypy src/`.
- All adapters must implement `TrademarkAPI` protocol (`domain/trademark/ports.py`): `async def search(phrase, nice_classes) → TrademarkSearchResult`. Never raise; return `error=` string on failure.
- Settings come from env vars (pydantic-settings). Secret values use `SecretStr`. Add new settings to `core/config.py` `Settings` class.
- `get_container()` is an LRU singleton; call `get_container.cache_clear()` in tests.
- Tests: pytest-asyncio (`asyncio_mode = "auto"`). 80% coverage floor. Mark with `@pytest.mark.unit` / `integration` / `slow`.

---

## Chrome Extension (apps/extension)

Vite + React + TypeScript. `pnpm dev:extension`. Outputs to `dist/`.

---

## Database

Supabase (Postgres). Migrations via Supabase CLI:
```
pnpm db:migrate:new   # create migration
pnpm db:push          # push to linked project
pnpm db:types         # regenerate packages/contracts/src/database.types.ts
```

---

## Known issues / current state

- **UKIPO 403**: `UKIPOClient` gets 403 from Cloudflare WAF on DigitalOcean IPs. Fails gracefully (returns empty results with `error="http_403"`). No full fix yet. See fix proposal below.
- **Common-law checker**: `NoOpCommonLawChecker` — always returns 0.0. Real Etsy-based checker is planned (Phase B).
- **Cache**: process-local `MemoryCache` only. Redis wired in settings but not active (`CACHE_PROVIDER=memory`).
- **Image gen**: disabled by default (`IMAGE_GEN_PROVIDER=disabled`).
- **Events (niche radar)**: static JSON only; Calendarific adapter is pending.

---

## Running everything

```bash
# Full dev (web + workers in parallel)
pnpm dev

# Individual
pnpm dev:web        # Next.js on :3000
pnpm dev:workers    # FastAPI on :8000
pnpm dev:extension  # Vite extension

# Tests
pnpm test           # all (turbo)
pnpm test:workers   # pytest only

# Lint + format
pnpm lint:fix       # TS/JS
cd apps/workers && uv run ruff check --fix && uv run ruff format .

# Type check
pnpm type-check             # TS
cd apps/workers && uv run mypy src/  # Python
```

---

## Environment variables (key ones)

```
# Supabase
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_JWT_SECRET=

# Trademark providers
US_TRADEMARK_PROVIDER=marker          # or "uspto"
MARKER_API_USERNAME=
MARKER_API_PASSWORD=
USPTO_API_KEY=                        # only if US_TRADEMARK_PROVIDER=uspto
EU_TRADEMARK_PROVIDER=tmview          # or "euipo"
UK_TRADEMARK_PROVIDER=tmview_uk        # default; or "ukipo" when running behind a residential proxy

# LLM
OPENAI_API_KEY=

# Optional paid
APIFY_API_TOKEN=
NICHE_MARKETPLACE_PROVIDER=etsy_public  # or "apify"
```
