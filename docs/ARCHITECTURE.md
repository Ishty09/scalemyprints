# Architecture

## Why Domain-Driven Design?

ScaleMyPrints will eventually integrate with 10+ external services (USPTO, EUIPO, IP Australia, OpenAI, Etsy, Amazon, Redbubble, Stripe, Resend, Cloudflare, Sentry, PostHog…) and offer 6 tools that each have their own business rules.

Without strict layering, the codebase becomes a maze where domain logic, HTTP serialization, and external API quirks tangle together. DDD's separation of concerns gives us:

1. **Testability** — domain logic runs in milliseconds with no I/O
2. **Provider swaps without rewrites** — `MemoryCache` → `RedisCache` is a one-line change
3. **Clear ownership** — when a bug appears, you know which layer to look in

## The four layers

```
┌──────────────────────────────────────────────────────────────┐
│  Presentation                                                │
│  apps/web  +  apps/extension                                 │
│  Knows about HTTP, cookies, React, Chrome APIs.              │
│  Talks to the API layer over JSON.                           │
└──────────────────────────────────────────────────────────────┘
                              ↓ HTTP
┌──────────────────────────────────────────────────────────────┐
│  API                                                         │
│  apps/workers/src/scalemyprints/api/                         │
│  - Routes: parse body → call domain → wrap envelope          │
│  - Middleware: request_id, auth, rate limit                  │
│  - Exception handlers: domain errors → ApiFailure            │
│  Knows about FastAPI, JWT, request shapes.                   │
└──────────────────────────────────────────────────────────────┘
                              ↓ method calls
┌──────────────────────────────────────────────────────────────┐
│  Domain                                                      │
│  apps/workers/src/scalemyprints/domain/                      │
│  - Entities, value objects (Pydantic models)                 │
│  - Pure services (RiskScorer, GenericnessCalculator, ...)    │
│  - Orchestrators (TrademarkSearchService)                    │
│  - Ports: Protocols describing what we need from outside     │
│  Knows ONLY about business rules. Zero I/O.                  │
└──────────────────────────────────────────────────────────────┘
                              ↑ implements ports
┌──────────────────────────────────────────────────────────────┐
│  Infrastructure                                              │
│  apps/workers/src/scalemyprints/infrastructure/              │
│  - HTTP adapters: USPTOClient, EUIPOClient, IPAustraliaClient│
│  - Cache: MemoryCache, RedisCache                            │
│  - Common-law checker: NoOpCommonLawChecker, EtsyChecker     │
│  - ServiceContainer composes everything                      │
│  Translates between external services and domain types.      │
└──────────────────────────────────────────────────────────────┘
```

## The dependency rule

**Code in inner layers cannot import from outer layers.**

- Domain ← does not import from API, Infrastructure, or Presentation
- API ← imports from Domain only (NOT from Infrastructure directly)
- Infrastructure ← imports from Domain only (to implement Protocols)
- Presentation ← imports nothing else

The dependency injection container (`infrastructure/container.py`) is the ONE place where all four layers are stitched together. FastAPI route handlers receive fully-wired services via `Depends()`.

## Why ports (Protocols) instead of abstract base classes?

```python
# Old style: ABC
from abc import ABC, abstractmethod

class TrademarkAPI(ABC):
    @abstractmethod
    async def search(self, phrase: str, nice_classes: list[int]) -> ...: ...

# Our style: Protocol
from typing import Protocol

class TrademarkAPI(Protocol):
    async def search(self, phrase: str, nice_classes: list[int]) -> ...: ...
```

`Protocol` lets us **add capabilities to existing classes without inheritance**. Test doubles, third-party clients, and our own adapters all satisfy `TrademarkAPI` without explicit declaration. Duck typing checked at type-check time.

## Why contracts (TS) ↔ models (Python) duplication?

We have `packages/contracts/src/trademark.ts` and `apps/workers/src/scalemyprints/domain/trademark/models.py` describing the same shapes.

Why not generate one from the other?

1. **Sync drift fails loudly.** Tests verify the shapes match. If they diverge, integration tests break — not silently.
2. **Native idioms in each language.** TS gets Zod with `z.infer<>`; Python gets Pydantic with `Field(...)`. Generation gives you the lowest common denominator.
3. **Different concerns.** TS contracts include UI labels (`RISK_LEVEL_LABELS`); Python models don't need them.

## Why memory cache before Redis?

In Phase A, we run a single worker. Process-local cache is sufficient and adds **zero** infrastructure cost. The `CacheStore` Protocol means we can swap to Redis when we have:

- Multiple workers behind a load balancer (need cache coherence)
- Workers that get restarted often (don't want to lose cache on every deploy)

The change is one line in `infrastructure/container.py`:

```python
# Before
self._cache: CacheStore = MemoryCache()
# After
self._cache: CacheStore = RedisCache(url=settings.redis_url)
```

No domain code changes. No tests break.

## Provider abstraction (LLM, payments, email)

Same pattern for every external dependency:

| Domain port             | Phase A implementation | Phase B+ swap                    |
| ----------------------- | ---------------------- | -------------------------------- |
| `LLMProvider`           | `OpenAIProvider`       | `ClaudeProvider`, `LocalProvider`|
| `PaymentProvider`       | `LemonSqueezyProvider` | `StripeProvider`                 |
| `EmailProvider`         | `ResendProvider`       | `PostmarkProvider`, `SESProvider`|
| `CacheStore`            | `MemoryCache`          | `RedisCache`                     |
| `CommonLawChecker`      | `NoOpChecker`          | `EtsyShopChecker`                |

Each Phase A implementation costs $0–$10/month. Swap-up only when revenue justifies it.

## Error handling philosophy

Errors are **values, not exceptions**, until they hit the API boundary.

Inside the domain:

- Pure functions return `Result[Ok, Err]` or `Optional[T]`
- Adapters that fail return `TrademarkSearchResult(error="timeout")` — they NEVER raise

At the API boundary:

- `AppError` subclasses with stable error codes get caught by `app_error_handler`
- Pydantic validation errors get caught by `validation_error_handler`
- Anything else gets caught by `unhandled_exception_handler` (logs full stack, returns generic 500)

Clients ALWAYS receive the same `ApiResponse<T>` shape:

```json
{ "ok": true, "data": {...}, "meta": {...} }
{ "ok": false, "error": { "code": "rate_limited", "message": "...", "details": {...}, "request_id": "..." } }
```

## Testing strategy

| Test type        | What it tests                          | Tools                       | Speed       |
| ---------------- | -------------------------------------- | --------------------------- | ----------- |
| Unit (domain)    | Pure logic, fakes for ports            | pytest                      | <1ms each   |
| Unit (infrastructure) | Adapters with mocked HTTP         | pytest + respx              | ~5ms each   |
| Integration      | Real FastAPI app, mocked external APIs | pytest + TestClient + respx | ~30ms each  |
| E2E (planned)    | Real Supabase + real APIs              | Playwright                  | seconds     |

Coverage targets:

- Domain: ≥ 90%
- Infrastructure: ≥ 80%
- API: ≥ 80%
- Overall: ≥ 80%

Current state: **87.47% across 200 tests.**

## Where to add new things

| What you're adding                    | Where it goes                                              |
| ------------------------------------- | ---------------------------------------------------------- |
| New trademark office (Japan, Canada)  | New file in `infrastructure/trademark_apis/`               |
| New scoring factor                    | `domain/trademark/scorer.py` — adjust weights              |
| New tool (e.g., Niche Radar)          | New domain folder + new infra adapters + new API routes    |
| New external service (e.g., Stripe)   | New port in domain + new adapter in infrastructure         |
| New API endpoint                      | New route file in `api/routes/` + tests in integration/    |
| New page                              | `apps/web/src/app/(group)/page.tsx` + components           |
| Shared brand value (color, copy)      | `packages/contracts/src/branding.ts`                       |

When in doubt, ask: *"Does this code know about HTTP, databases, or the file system?"* If yes → infrastructure. If no → domain.
