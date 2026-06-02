"""
Supabase-backed monthly design quota.

Uses a `design_quota` table keyed by (user_id, month_bucket). Each
design generation that succeeds bumps `used_count` atomically via the
`increment_design_quota` Postgres RPC defined in the migration.

Plans not found resolve to FREE_TIER (5 designs/month).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial

from supabase import Client, create_client

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.models import QuotaSnapshot
from scalemyprints.domain.design.plan_quotas import (
    UNLIMITED,
    is_unlimited,
    quota_for_plan,
)
from scalemyprints.domain.design.ports import QuotaCheck, QuotaService
from scalemyprints.infrastructure.quota.plan_resolver import (
    PlanResolver,
    StaticPlanResolver,
    SupabasePlanResolver,
)

logger = get_logger(__name__)

TABLE = "design_quota"
INCREMENT_RPC = "increment_design_quota"


def _current_month_bucket() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _next_month_start() -> datetime:
    now = datetime.now(UTC)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1, tzinfo=UTC)
    return datetime(now.year, now.month + 1, 1, tzinfo=UTC)


class SupabaseDesignQuota(QuotaService):
    """Plan-aware monthly quota tracker backed by Supabase."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
        plan_resolver: PlanResolver | None = None,
    ) -> None:
        if not supabase_url or not service_role_key:
            raise ValueError("supabase_url + service_role_key required")
        self._client: Client = create_client(supabase_url, service_role_key)
        self._plan_resolver: PlanResolver = plan_resolver or SupabasePlanResolver(
            client=self._client,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def snapshot(self, user_id: str) -> QuotaSnapshot:
        plan = await self._plan_resolver.resolve(user_id)
        limit = quota_for_plan(plan)
        used = await self._used_count(user_id, _current_month_bucket())
        remaining = UNLIMITED if is_unlimited(limit) else max(limit - used, 0)
        return QuotaSnapshot(
            user_id=user_id,
            plan=plan,
            month_bucket=_current_month_bucket(),
            monthly_limit=limit,
            used=used,
            remaining=remaining,
            resets_at=_next_month_start(),
        )

    async def pre_check(
        self,
        user_id: str,
        *,
        requested: int = 1,
    ) -> QuotaCheck:
        snap = await self.snapshot(user_id)
        if is_unlimited(snap.monthly_limit):
            return QuotaCheck(
                allowed=True,
                plan=snap.plan,
                monthly_limit=snap.monthly_limit,
                used=snap.used,
                remaining=UNLIMITED,
            )
        will_use = snap.used + requested
        return QuotaCheck(
            allowed=will_use <= snap.monthly_limit,
            plan=snap.plan,
            monthly_limit=snap.monthly_limit,
            used=snap.used,
            remaining=max(snap.monthly_limit - snap.used, 0),
        )

    async def commit(self, user_id: str, *, count: int = 1) -> None:
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                partial(
                    self._client.rpc(
                        INCREMENT_RPC,
                        {
                            "p_user_id": user_id,
                            "p_month_bucket": _current_month_bucket(),
                            "p_increment": count,
                        },
                    ).execute
                ),
            )
        except Exception as e:
            logger.warning(
                "design_quota_commit_rpc_failed",
                user_id=user_id,
                error=str(e)[:200],
            )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _used_count(self, user_id: str, month_bucket: str) -> int:
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                partial(
                    self._client.table(TABLE)
                    .select("used_count")
                    .eq("user_id", user_id)
                    .eq("month_bucket", month_bucket)
                    .single()
                    .execute
                ),
            )
        except Exception:
            return 0
        row = getattr(result, "data", None) or {}
        return int(row.get("used_count") or 0)


class MemoryDesignQuota(QuotaService):
    """In-memory fallback used in dev/tests when Supabase is missing."""

    def __init__(
        self,
        *,
        plan_resolver: PlanResolver | None = None,
    ) -> None:
        self._plan_resolver: PlanResolver = plan_resolver or StaticPlanResolver()
        self._used: dict[tuple[str, str], int] = {}
        self._lock = asyncio.Lock()

    async def snapshot(self, user_id: str) -> QuotaSnapshot:
        plan = await self._plan_resolver.resolve(user_id)
        bucket = _current_month_bucket()
        async with self._lock:
            used = self._used.get((user_id, bucket), 0)
        limit = quota_for_plan(plan)
        remaining = UNLIMITED if is_unlimited(limit) else max(limit - used, 0)
        return QuotaSnapshot(
            user_id=user_id,
            plan=plan,
            month_bucket=bucket,
            monthly_limit=limit,
            used=used,
            remaining=remaining,
            resets_at=_next_month_start(),
        )

    async def pre_check(
        self,
        user_id: str,
        *,
        requested: int = 1,
    ) -> QuotaCheck:
        snap = await self.snapshot(user_id)
        if is_unlimited(snap.monthly_limit):
            return QuotaCheck(
                allowed=True,
                plan=snap.plan,
                monthly_limit=snap.monthly_limit,
                used=snap.used,
                remaining=UNLIMITED,
            )
        return QuotaCheck(
            allowed=(snap.used + requested) <= snap.monthly_limit,
            plan=snap.plan,
            monthly_limit=snap.monthly_limit,
            used=snap.used,
            remaining=max(snap.monthly_limit - snap.used, 0),
        )

    async def commit(self, user_id: str, *, count: int = 1) -> None:
        bucket = _current_month_bucket()
        async with self._lock:
            self._used[(user_id, bucket)] = self._used.get((user_id, bucket), 0) + count
