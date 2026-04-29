"""
API layer — FastAPI surface.

Rules:
- Routes are THIN: parse, authorize, dispatch to domain, format response
- No business logic here — it lives in domain/
- All exceptions handled centrally (exception_handlers.py)
- Responses wrapped in ApiResponse<T> envelope
"""
