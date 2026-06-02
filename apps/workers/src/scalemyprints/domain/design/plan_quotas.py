"""
Plan-tier → monthly design quota mapping.

Mirrors packages/contracts/src/pricing.ts (Bundles + tool plans).
The QuotaService consults this table to know how many designs a user
on plan X may generate per month.

Update both this file and pricing.ts when plan limits change.
"""

from __future__ import annotations

from typing import Final

UNLIMITED: Final[int] = -1

# Plan slug → monthly limit. Plans not listed default to FREE_TIER.
PLAN_DESIGN_QUOTAS: dict[str, int] = {
    "free": 5,  # taste of the product
    "starter": 50,
    "pro": 200,
    "agency": UNLIMITED,
    # Bundles — what the user is most likely on
    "core_bundle": 200,
    "pro_bundle": 500,
    "empire_bundle": UNLIMITED,
    # Founding-member overrides applied on top by QuotaService.
}

FREE_TIER_LIMIT: Final[int] = PLAN_DESIGN_QUOTAS["free"]


def quota_for_plan(plan: str | None) -> int:
    """Resolve the monthly design quota for a plan slug."""
    if not plan:
        return FREE_TIER_LIMIT
    return PLAN_DESIGN_QUOTAS.get(plan.lower(), FREE_TIER_LIMIT)


def is_unlimited(limit: int) -> bool:
    return limit == UNLIMITED
