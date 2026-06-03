"""
Live printer-price adapters — Printful + Printify catalog APIs.

Used by `profit_service.compute()` to pull fresh per-product base
costs instead of the static 2026-Q2 tables. Adapters NEVER raise;
on failure the caller falls back to the static numbers.
"""
