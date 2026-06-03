"""
Alert dispatcher implementations for the Phase 4 watchlist engine.

Each dispatcher implements `AlertDispatcher` and handles a single
channel. The container wires them up based on Settings — missing
credentials degrade to a no-op rather than failing.
"""
