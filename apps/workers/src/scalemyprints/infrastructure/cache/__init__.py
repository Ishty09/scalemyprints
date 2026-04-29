"""
Cache adapters.

Implementations of domain.trademark.ports.CacheStore.
"""

from scalemyprints.infrastructure.cache.memory import MemoryCache

__all__ = ["MemoryCache"]
