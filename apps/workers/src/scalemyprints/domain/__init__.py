"""
Domain layer — pure business logic.

Rules:
- No I/O, no network, no database access
- All dependencies injected via constructor (ports)
- All logic testable with simple fakes
- Domain models validated via Pydantic
"""
