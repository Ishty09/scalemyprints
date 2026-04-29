"""
FastAPI dependencies (DI providers).

Centralizes how routes obtain services. If we change how a dependency is
created, routes don't need to change.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from scalemyprints.core.config import Settings, get_settings
from scalemyprints.domain.niche.search_service import NicheSearchService
from scalemyprints.domain.trademark.search_service import TrademarkSearchService
from scalemyprints.infrastructure.container import ServiceContainer, get_container


def get_service_container() -> ServiceContainer:
    """Return the process-wide ServiceContainer."""
    return get_container()


def get_settings_dep() -> Settings:
    """Return process-wide settings (FastAPI-friendly wrapper)."""
    return get_settings()


def get_trademark_search_service(
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> TrademarkSearchService:
    """Return a trademark search service wired with current config."""
    return container.build_trademark_search_service()


def get_niche_search_service(
    container: Annotated[ServiceContainer, Depends(get_service_container)],
) -> NicheSearchService:
    """Return a niche search service wired with current config."""
    return container.build_niche_search_service()
