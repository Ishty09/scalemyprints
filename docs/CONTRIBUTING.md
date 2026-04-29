# Contributing

## Workflow

1. Branch from `main`: `git checkout -b feat/short-description`
2. Make changes
3. Add tests
4. Run `pnpm lint && pnpm type-check && pnpm test` locally
5. Push and open a PR

CI must pass before merge: lint, type-check, tests, and build for all three apps.

## Commit messages

Conventional commits, lowercase scope:

```
feat(workers): add EUIPO opposition status normalizer
fix(web): correct redirect path on signup
docs(architecture): clarify Protocol vs ABC choice
chore(ci): bump pytest to 8.1.1
test(domain): add edge case for adjacent class scoring
```

Append `[skip deploy]` to commit messages on `main` to skip the production deploy (e.g., docs-only changes).

## Code style

### Python (workers)

- Format: `ruff format`
- Lint: `ruff check`
- Type check: `mypy`
- Imports: `from __future__ import annotations` at the top of every file
- Type hints: required everywhere, including return types
- Async: use `async def` for anything that does I/O; pure functions stay sync
- Docstrings: Google style for public functions, single-line for private

### TypeScript (web, extension, contracts)

- Format: Prettier (configured in `.prettierrc.json`)
- Lint: ESLint (Next.js config for web, custom for extension)
- Strict TypeScript everywhere; no `any` without comment justifying it
- Prefer `type` over `interface` for shapes that don't extend
- React: function components only, named exports preferred

## Testing requirements

| Layer            | Coverage target | What's required                                    |
| ---------------- | --------------- | -------------------------------------------------- |
| Domain (Python)  | ≥ 90%           | Every public function unit-tested with fakes      |
| Infrastructure   | ≥ 80%           | Adapters tested with `respx` HTTP mocking         |
| API (Python)     | ≥ 80%           | Routes tested via `TestClient` + `dependency_overrides` |
| Web components   | flexible        | Visual + behavioral correctness via Vitest + RTL  |

When adding a new feature:

- Domain change → write the test first (TDD encouraged)
- Infrastructure change → mock the external service with `respx`
- New API endpoint → integration test in `tests/integration/`

## Review checklist

Reviewers should ask:

- Does the layering hold? (domain doesn't import infrastructure, etc.)
- Are errors values or exceptions in the right places?
- Are new ports added to `ServiceContainer`?
- Are new error codes added to both Python `errors.py` and TS `errors.ts`?
- Are tests deterministic (no real network, no real time)?
- Is the public API documented?

## Adding a new tool (e.g., Niche Radar)

1. Add to `packages/contracts/src/branding.ts` → `TOOLS`
2. Add to `packages/contracts/src/pricing.ts` if it has its own pricing
3. Domain folder: `apps/workers/src/scalemyprints/domain/niche_radar/`
   - `enums.py`, `models.py`, `ports.py`, `service.py`
4. Infrastructure: `apps/workers/src/scalemyprints/infrastructure/niche_radar/`
   - Implementations of the ports
5. API: `apps/workers/src/scalemyprints/api/routes/niche_radar.py`
6. Wire into `infrastructure/container.py`
7. Web: `apps/web/src/app/(app)/dashboard/niche-radar/page.tsx`
8. Tests at every layer

## Reporting issues

- Bugs: open a GitHub issue with reproduction steps
- Security: email security@scalemyprints.com (do not open a public issue)
- Feature ideas: discuss in the team Slack `#product` channel before opening an issue
