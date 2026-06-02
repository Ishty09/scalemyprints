"""API route modules."""

from scalemyprints.api.routes.design import router as design_router
from scalemyprints.api.routes.health import router as health_router
from scalemyprints.api.routes.niche import router as niche_router
from scalemyprints.api.routes.trademark import router as trademark_router

__all__ = [
    "design_router",
    "health_router",
    "niche_router",
    "trademark_router",
]
