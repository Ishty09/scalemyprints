# @scalemyprints/contracts

**Single source of truth** for types shared between the web app, Chrome extension, and Python workers.

## Modules

| Module          | Purpose                                                             |
| --------------- | ------------------------------------------------------------------- |
| `branding`      | Brand constants, tool registry, colors, social links                |
| `pricing`       | Plans, tiers, bundles, limits, founding member config               |
| `api`           | Response envelope (`ApiResponse<T>`), error codes, pagination       |
| `errors`        | Typed error classes (`AppError`, `ValidationError`, etc.)           |
| `auth`          | User profiles, subscriptions, signup/login schemas, waitlist        |
| `trademark`     | Core Phase A contracts for Trademark Shield                         |

## Usage

```ts
import {
  type TrademarkSearchRequest,
  TRADEMARK_SEARCH_REQUEST_SCHEMA,
  BRAND,
  BUNDLES,
  buildSuccess,
  buildFailure,
  ERROR_CODES,
} from '@scalemyprints/contracts'
```

## Rules

1. **No side effects.** This package only exports types and constants.
2. **Zod-first.** Runtime-validated data at app boundaries uses Zod schemas.
3. **Mirror in Python.** Types with matching Pydantic models in `apps/workers` must stay in sync. If you change one, change the other.
4. **No app imports.** This package must not import from `apps/*`.

## Python mirroring

See `apps/workers/src/scalemyprints/api/schemas/` — Pydantic models mirror these TS schemas field-for-field. When you change one side, update the other and run tests.
