"""MemoryDesignQuota — pre-check / commit / unlimited semantics."""

from __future__ import annotations

import pytest

from scalemyprints.infrastructure.quota.plan_resolver import StaticPlanResolver
from scalemyprints.infrastructure.quota.supabase_quota import MemoryDesignQuota


@pytest.mark.unit
class TestMemoryDesignQuota:
    async def test_free_tier_initial_state(self) -> None:
        quota = MemoryDesignQuota(plan_resolver=StaticPlanResolver(default_plan="free"))
        snap = await quota.snapshot("u1")

        assert snap.plan == "free"
        assert snap.monthly_limit == 5
        assert snap.used == 0
        assert snap.remaining == 5

    async def test_pre_check_allows_within_limit(self) -> None:
        quota = MemoryDesignQuota(plan_resolver=StaticPlanResolver(default_plan="free"))
        check = await quota.pre_check("u1", requested=3)
        assert check.allowed is True

    async def test_pre_check_blocks_over_limit(self) -> None:
        quota = MemoryDesignQuota(plan_resolver=StaticPlanResolver(default_plan="free"))
        # Free tier = 5 per month
        for _ in range(5):
            await quota.commit("u1", count=1)

        check = await quota.pre_check("u1", requested=1)
        assert check.allowed is False
        assert check.remaining == 0

    async def test_pre_check_allows_burst_within_remaining(self) -> None:
        quota = MemoryDesignQuota(plan_resolver=StaticPlanResolver(default_plan="free"))
        await quota.commit("u1", count=2)

        check_2 = await quota.pre_check("u1", requested=3)
        assert check_2.allowed is True
        check_4 = await quota.pre_check("u1", requested=4)
        assert check_4.allowed is False

    async def test_unlimited_plan_never_blocks(self) -> None:
        quota = MemoryDesignQuota(
            plan_resolver=StaticPlanResolver(default_plan="agency"),
        )
        for _ in range(50):
            await quota.commit("u1", count=10)
        check = await quota.pre_check("u1", requested=999)
        assert check.allowed is True
        assert check.monthly_limit == -1
        assert check.remaining == -1

    async def test_quota_isolated_per_user(self) -> None:
        quota = MemoryDesignQuota(plan_resolver=StaticPlanResolver(default_plan="free"))
        for _ in range(5):
            await quota.commit("u1", count=1)

        snap_u1 = await quota.snapshot("u1")
        snap_u2 = await quota.snapshot("u2")

        assert snap_u1.used == 5
        assert snap_u2.used == 0
