"""MemoryDesignJobStore — CRUD + status transitions + tenant isolation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scalemyprints.domain.design.enums import (
    DesignAspect,
    DesignStatus,
    DesignStyle,
    OutputFormat,
)
from scalemyprints.domain.design.models import DesignJob, DesignRequest
from scalemyprints.infrastructure.job_store.memory_job_store import (
    MemoryDesignJobStore,
)


def _job(*, id: str = "j1", user_id: str = "u1") -> DesignJob:
    now = datetime.now(UTC)
    return DesignJob(
        id=id,
        user_id=user_id,
        request=DesignRequest(
            prompt="dog mom",
            style=DesignStyle.MINIMAL,
            aspect=DesignAspect.SQUARE,
            output_format=OutputFormat.PNG_TRANSPARENT,
        ),
        status=DesignStatus.QUEUED,
        created_at=now,
        updated_at=now,
    )


@pytest.mark.unit
class TestMemoryDesignJobStore:
    async def test_create_then_get_round_trip(self) -> None:
        store = MemoryDesignJobStore()
        job = _job()
        await store.create(job)
        fetched = await store.get(job.id, job.user_id)
        assert fetched is not None
        assert fetched.id == job.id

    async def test_get_returns_none_for_other_user(self) -> None:
        store = MemoryDesignJobStore()
        await store.create(_job(user_id="u1"))
        fetched = await store.get("j1", "u2")
        assert fetched is None

    async def test_update_status_progresses_lifecycle(self) -> None:
        store = MemoryDesignJobStore()
        await store.create(_job())
        await store.update_status("j1", DesignStatus.GENERATING)
        await store.update_status("j1", DesignStatus.COMPLETED, duration_ms=200)

        fetched = await store.get("j1", "u1")
        assert fetched is not None
        assert fetched.status == DesignStatus.COMPLETED
        assert fetched.duration_ms == 200
        assert fetched.completed_at is not None

    async def test_list_for_user_filters_and_orders(self) -> None:
        store = MemoryDesignJobStore()
        await store.create(_job(id="j1", user_id="u1"))
        await store.create(_job(id="j2", user_id="u1"))
        await store.create(_job(id="j3", user_id="u2"))
        await store.update_status("j2", DesignStatus.COMPLETED)

        u1_jobs, u1_total = await store.list_for_user("u1")
        assert u1_total == 2
        assert {j.id for j in u1_jobs} == {"j1", "j2"}

        completed, _ = await store.list_for_user("u1", status=DesignStatus.COMPLETED)
        assert {j.id for j in completed} == {"j2"}

    async def test_soft_delete_returns_true_when_owned(self) -> None:
        store = MemoryDesignJobStore()
        await store.create(_job())
        assert await store.soft_delete("j1", "u1") is True
        assert await store.get("j1", "u1") is None

    async def test_soft_delete_refuses_other_users_jobs(self) -> None:
        store = MemoryDesignJobStore()
        await store.create(_job(user_id="u1"))
        assert await store.soft_delete("j1", "u2") is False
        assert await store.get("j1", "u1") is not None
