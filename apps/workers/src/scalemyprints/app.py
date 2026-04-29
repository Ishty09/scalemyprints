"""
FastAPI application factory.

Usage:
    from scalemyprints.app import create_app
    app = create_app()

Production entry point (see main.py):
    uvicorn scalemyprints.main:app
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sentry_sdk.integrations.fastapi import FastApiIntegration

from scalemyprints import __version__
from scalemyprints.api.exception_handlers import register_exception_handlers
from scalemyprints.api.middleware.request_context import RequestContextMiddleware
from scalemyprints.api.routes import health_router, niche_router, trademark_router
from scalemyprints.core.config import Settings, get_settings
from scalemyprints.core.logging import configure_logging, get_logger
from scalemyprints.infrastructure.container import get_container

logger = get_logger(__name__)


def _init_sentry(settings: Settings) -> None:
    """Initialize Sentry if DSN is configured."""
    if not settings.sentry_dsn:
        logger.info("sentry_not_configured")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[FastApiIntegration()],
        environment=settings.sentry_environment,
        release=f"scalemyprints-workers@{__version__}",
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        profiles_sample_rate=0.1 if settings.is_production else 0.0,
        send_default_pii=False,  # privacy: don't auto-attach user data
    )
    logger.info("sentry_initialized", environment=settings.sentry_environment)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Startup/shutdown lifecycle.

    Warm up the service container at startup so the first request isn't
    slow. Close HTTP clients cleanly at shutdown.
    """
    settings = get_settings()
    logger.info(
        "app_starting",
        version=__version__,
        environment=settings.environment.value,
    )
    container = get_container()
    app.state.container = container

    try:
        yield
    finally:
        await container.aclose()
        logger.info("app_stopped")


def create_app() -> FastAPI:
    """Construct the FastAPI application."""
    configure_logging()
    settings = get_settings()
    _init_sentry(settings)

    app = FastAPI(
        title="ScaleMyPrints API",
        description="AI workforce for Print-on-Demand sellers",
        version=__version__,
        lifespan=_lifespan,
        # Show docs in dev, hide in production
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    # CORS — must come before RequestContextMiddleware so headers are set first
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # Our request context middleware (logs, request IDs)
    app.add_middleware(RequestContextMiddleware)

    # Exception handlers
    register_exception_handlers(app)

    # Routers
    app.include_router(health_router)
    app.include_router(trademark_router)
    app.include_router(niche_router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": "ScaleMyPrints API",
            "version": __version__,
            "docs": "/docs" if not settings.is_production else "hidden",
        }

    return app
