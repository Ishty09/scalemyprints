"""Plan-tier quota mapping."""

from __future__ import annotations

import pytest

from scalemyprints.domain.design.plan_quotas import (
    UNLIMITED,
    is_unlimited,
    quota_for_plan,
)


@pytest.mark.unit
class TestPlanQuotas:
    def test_known_plans(self) -> None:
        assert quota_for_plan("free") == 5
        assert quota_for_plan("starter") == 50
        assert quota_for_plan("pro") == 200
        assert quota_for_plan("agency") == UNLIMITED
        assert quota_for_plan("core_bundle") == 200
        assert quota_for_plan("pro_bundle") == 500
        assert quota_for_plan("empire_bundle") == UNLIMITED

    def test_unknown_plan_falls_back_to_free(self) -> None:
        assert quota_for_plan("does_not_exist") == 5
        assert quota_for_plan(None) == 5
        assert quota_for_plan("") == 5

    def test_case_insensitive(self) -> None:
        assert quota_for_plan("PRO") == 200
        assert quota_for_plan("Core_Bundle") == 200

    def test_is_unlimited(self) -> None:
        assert is_unlimited(UNLIMITED) is True
        assert is_unlimited(0) is False
        assert is_unlimited(1) is False
        assert is_unlimited(200) is False
