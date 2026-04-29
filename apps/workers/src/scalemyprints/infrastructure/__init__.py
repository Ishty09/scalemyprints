"""
Infrastructure layer — external adapters.

Implements the Protocols defined in the domain layer:
- TrademarkAPI → uspto.py, euipo.py, ipau.py
- CacheStore → memory.py, redis_cache.py
- CommonLawChecker → no_op.py (Phase A), etsy_checker.py (Phase B+)

Each adapter is a thin translator between external services and normalized
domain types. No business logic lives here.
"""
