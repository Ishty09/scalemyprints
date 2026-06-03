"""API route modules."""

from scalemyprints.api.routes.health import router as health_router
from scalemyprints.api.routes.niche import router as niche_router
from scalemyprints.api.routes.spy import router as spy_router
from scalemyprints.api.routes.spy_public import router as spy_public_router
from scalemyprints.api.routes.trademark import router as trademark_router

__all__ = [
    "health_router",
    "niche_router",
    "spy_router",
    "spy_public_router",
    "trademark_router",
]
