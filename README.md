# ScaleMyPrints

> Your AI workforce for Print-on-Demand sellers.

A monorepo containing six AI-powered tools that automate trend research, design generation, trademark checking, competitor tracking, multi-platform listing, and analytics for POD sellers.

**Phase A scope (current):** Trademark Shield + Chrome Extension. Five additional tools shipping in subsequent phases.

---

## Repository structure

```
scalemyprints/
├── apps/
│   ├── web/                Next.js 14 marketing site + dashboard
│   ├── workers/            Python FastAPI backend (domain-driven)
│   └── extension/          Manifest V3 Chrome extension
├── packages/
│   ├── contracts/          Shared TypeScript contracts (Zod-validated)
│   ├── utils/              Platform-agnostic TypeScript utilities
│   └── config/             Shared TS, ESLint, Tailwind, Prettier configs
├── infra/
│   ├── docker/             Dockerfile + docker-compose for workers
│   ├── scripts/            Deploy scripts
│   └── supabase/           SQL migrations + local config
├── docs/                   Architecture, deployment, contributing
└── .github/workflows/      CI + deploy pipelines
```

---

## Quickstart

### Prerequisites

- Node.js 20+ and pnpm 8.15+
- Python 3.11+ and [uv](https://github.com/astral-sh/uv)
- Docker (for containerized worker testing)
- A Supabase project ([create one free](https://supabase.com))

### 1. Install

```bash
# Clone
git clone https://github.com/scalemyprints/scalemyprints.git
cd scalemyprints

# Install Node deps for all workspace packages
pnpm install

# Install Python deps for workers
cd apps/workers
uv pip install --system -e ".[dev]"
cd ../..
```

### 2. Configure environment

```bash
cp .env.example .env.local
# Fill in Supabase URL + anon key (see .env.example for full list)
```

For the web app, also:

```bash
cp apps/web/.env.example apps/web/.env.local
```

For workers, the same `.env` works — they read from the root.

### 3. Set up Supabase

```bash
# If you haven't yet, install the CLI
npm install -g supabase

# Link to your project (one-time)
cd infra/supabase
supabase link --project-ref <your-project-ref>

# Push migrations
supabase db push
```

### 4. Run

In four terminals (or use `pnpm dev` for parallel):

```bash
# Terminal 1: workers
cd apps/workers
PYTHONPATH=src uv run uvicorn scalemyprints.main:app --reload --port 8000

# Terminal 2: web
pnpm --filter @scalemyprints/web dev

# Terminal 3: extension (rebuilds on file change)
pnpm --filter @scalemyprints/extension dev

# Terminal 4: load extension in Chrome
# Visit chrome://extensions, enable Developer Mode,
# click "Load unpacked" and select apps/extension/dist
```

Visit:

- http://localhost:3000 — marketing + dashboard
- http://localhost:8000/docs — interactive API docs
- Any Etsy/Amazon/Redbubble listing — extension widget appears bottom-right

---

## Common commands

```bash
# Run everything in parallel
pnpm dev

# Run all tests
pnpm test                                 # JS/TS tests
pnpm --filter @scalemyprints/workers test # Python tests

# Lint everything
pnpm lint

# Type-check everything
pnpm type-check

# Format
pnpm format

# Clean
pnpm clean
```

For workers specifically:

```bash
cd apps/workers
uv run pytest                    # All tests
uv run pytest tests/unit/        # Unit tests only (fast)
uv run pytest tests/integration/ # Integration tests
uv run ruff check src tests      # Lint
uv run ruff format src tests     # Format
uv run mypy src                  # Type check
```

---

## Architecture overview

We use **Domain-Driven Design** with strict layering:

```
┌─────────────────────────────────────────────────────────┐
│  apps/web  +  apps/extension                            │  Presentation
│      ↓ HTTP                                             │
├─────────────────────────────────────────────────────────┤
│  apps/workers/api/         FastAPI routes               │  API
│      ↓ thin dispatch                                    │
├─────────────────────────────────────────────────────────┤
│  apps/workers/domain/      Pure business logic          │  Domain
│      ↑ ports (Protocols)                                │
├─────────────────────────────────────────────────────────┤
│  apps/workers/infrastructure/  Adapters: USPTO, EUIPO,  │  Infrastructure
│                                ATMOSS, cache, etc.      │
└─────────────────────────────────────────────────────────┘
```

**Key principles:**

1. **Domain has zero I/O.** All external access happens through `Protocol`s defined in the domain; the infrastructure layer implements them.
2. **Type contracts are source of truth.** `packages/contracts` defines Zod schemas; Python Pydantic models mirror them field-for-field.
3. **Tests at every layer.** 200+ tests, 87% coverage. Domain tests use in-memory fakes (no I/O); integration tests spin up the real FastAPI app with mocked HTTP.
4. **Provider abstraction = free→paid scaling.** Switch `CACHE_PROVIDER=memory` to `redis`, or `LLM_PROVIDER=openai` to `claude` without touching code.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full picture.

---

## Tech stack

| Layer            | Tools                                                            |
| ---------------- | ---------------------------------------------------------------- |
| Frontend         | Next.js 14 (App Router), React 18, TypeScript, Tailwind, React Query |
| Auth & DB        | Supabase (Postgres + Auth + RLS)                                 |
| Backend          | Python 3.11, FastAPI, Pydantic v2, structlog, httpx, tenacity    |
| Trademark APIs   | USPTO Open Data Portal, EUIPO eSearch, IP Australia ATMOSS       |
| LLM (Phase A)    | OpenAI gpt-4o-mini (with provider abstraction for swap)          |
| Cache            | In-process LRU (Phase A) → Redis (Phase B)                       |
| Extension        | Vite + Manifest V3 + Shadow DOM widget                           |
| Observability    | structlog, Sentry, PostHog                                       |
| CI/CD            | GitHub Actions                                                   |
| Hosting          | Cloudflare Pages (web), Hetzner VPS (workers)                    |
| Payments (Phase D)| Lemon Squeezy (no LLC required initially)                       |

---

## Phased rollout

| Phase | Scope                                              | Status   |
| ----- | -------------------------------------------------- | -------- |
| A     | Build MVP (Trademark Shield + Chrome extension)    | ✅ shipped |
| B     | Beta validation — 20 invited users                 | ⏳ next   |
| C     | Pre-revenue prep (legal docs, payment setup)       |          |
| D     | Revenue go-live (Lemon Squeezy)                    |          |
| E     | Scale (LLC via Stripe Atlas, paid infrastructure)  |          |

Spending only ramps up after each phase's validation gate. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

---

## Contributing

See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md). Key conventions:

- Branch from `main`, PR back to `main`
- All checks must pass: lint + type-check + tests
- Domain changes require unit tests (90%+ target coverage on domain)
- Infrastructure changes require integration tests with `respx` for HTTP mocking
- Frontend changes should compile with strict TypeScript and pass `next lint`

---

## License

Proprietary. © 2026 ScaleMyPrints LLC.
#   s c a l e m y p r i n t s  
 