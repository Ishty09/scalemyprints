# @scalemyprints/workers

Python FastAPI backend for ScaleMyPrints.

## Architecture

This service follows **Domain-Driven Design** with clear layer separation:

```
src/scalemyprints/
├── core/              # Cross-cutting concerns: config, logging, errors
├── domain/            # Pure business logic — NO I/O, fully testable
│   ├── shared/        # Shared primitives (Result, Clock)
│   └── trademark/     # Trademark Shield domain
├── infrastructure/    # External adapters: DB, HTTP, cache, LLMs
└── api/               # FastAPI routes, middleware, schemas (thin)
```

## Design principles

1. **Dependency inversion** — Domain defines protocols (ports); infrastructure implements them.
2. **No I/O in domain** — Domain services accept ports as constructor args, not concrete classes.
3. **Pure functions for logic** — Scoring, validation, recommendation generation have zero side effects.
4. **Pydantic for boundaries** — All inputs/outputs validated; never trust raw dicts.
5. **Structured logging** — `structlog` with request_id context in every log line.

## Running

```bash
# Install uv if not already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync --all-extras

# Run dev server
uv run uvicorn scalemyprints.main:app --reload

# Run tests
uv run pytest

# Lint + format
uv run ruff check --fix src tests
uv run ruff format src tests

# Type check
uv run mypy src
```

## Testing layers

- **Unit tests** (`tests/unit/`) — domain logic only, no I/O, run in ms
- **Integration tests** (`tests/integration/`) — test infrastructure adapters against real services (run in CI separately)

## Adding a new feature

1. Define domain models in `domain/<feature>/models.py` (mirror TS contracts)
2. Define ports (protocols) the domain needs in `domain/<feature>/ports.py`
3. Write pure domain logic (services, scorers, validators)
4. Write unit tests — domain should be 90%+ covered
5. Implement infrastructure adapters in `infrastructure/`
6. Expose via API routes in `api/routes/`
