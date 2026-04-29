"""
Health and readiness probes.

- /health → liveness (is the process up?)
- /ready  → readiness (can we serve traffic? downstream deps reachable?)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from scalemyprints import __version__
from scalemyprints.api.schemas.envelope import ApiSuccess, success
from scalemyprints.core.config import get_settings

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    status: Literal["ok"] = "ok"
    version: str
    environment: str


class ReadyStatus(BaseModel):
    status: Literal["ready", "degraded"]
    version: str
    environment: str
    checks: dict[str, bool]


@router.get("/health", response_model=ApiSuccess[HealthStatus])
async def health() -> ApiSuccess[HealthStatus]:
    """Liveness check. Should always return 200 if the process is responsive."""
    settings = get_settings()
    return success(
        HealthStatus(
            version=__version__,
            environment=settings.environment.value,
        )
    )


@router.get("/ready", response_model=ApiSuccess[ReadyStatus])
async def ready() -> ApiSuccess[ReadyStatus]:
    """
    Readiness check.

    Phase A: just returns ok. Phase B: check DB, Redis, etc. reachability
    and return 'degraded' if any fail.
    """
    settings = get_settings()
    checks = {
        # Phase A has no hard dependencies at startup
        "config": True,
    }
    all_ok = all(checks.values())
    return success(
        ReadyStatus(
            status="ready" if all_ok else "degraded",
            version=__version__,
            environment=settings.environment.value,
            checks=checks,
        )
    )
