"""
Resolve a user's plan slug.

For Phase A we look up `subscriptions` (or `user_plans`) in Supabase to
find the user's active plan. If no row, the user is on FREE.

Production deployments may swap this for a Stripe / Lemon-Squeezy
adapter — keep the interface narrow.
"""

from __future__ import annotations

import asyncio
from functools import partial
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from supabase import Client


@runtime_checkable
class PlanResolver(Protocol):
    """Looks up a user's active plan slug."""

    async def resolve(self, user_id: str) -> str: ...


class StaticPlanResolver(PlanResolver):
    """Always returns the configured default plan — useful for dev."""

    def __init__(self, default_plan: str = "free") -> None:
        self._default = default_plan

    async def resolve(self, user_id: str) -> str:
        return self._default


class SupabasePlanResolver(PlanResolver):
    """
    Reads the user's plan from the `user_plans` table.

    Schema assumption (created in migration 0001_design_engine.sql):
        user_plans (
          user_id uuid pk,
          plan text not null default 'free',
          status text default 'active',
          updated_at timestamptz
        )
    Falls back to "free" when no row exists.
    """

    TABLE = "user_plans"

    def __init__(
        self,
        *,
        client: Client,
        default_plan: str = "free",
    ) -> None:
        self._client = client
        self._default = default_plan

    async def resolve(self, user_id: str) -> str:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(
                    self._client.table(self.TABLE)
                    .select("plan,status")
                    .eq("user_id", user_id)
                    .single()
                    .execute
                ),
            )
        except Exception:
            return self._default
        row = getattr(result, "data", None) or {}
        plan = (row.get("plan") or self._default).lower()
        status = (row.get("status") or "active").lower()
        if status not in {"active", "trialing"}:
            return self._default
        return plan
