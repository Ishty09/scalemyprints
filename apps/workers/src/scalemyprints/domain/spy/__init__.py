"""
Spy — POD market intelligence domain.

Cross-platform competitor research, velocity tracking, reverse design
search, viral mining, shop teardown, and risk overlays.

Domain depends only on Protocol ports defined in `ports.py`. All
concrete data sources (Etsy, Merch, Redbubble, etc.) live under
`infrastructure/spy_apis/` and never leak into the domain.

Adapters NEVER raise — they return Result objects with `error` set on
failure. The orchestrators decide how to escalate.
"""
