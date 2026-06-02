"""
In-memory DesignJobStore — dev/test fallback when Supabase isn't wired.

Process-local; lost on restart. Useful for local `pnpm dev:workers`
without a Supabase project.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from scalemyprints.domain.design.enums import DesignStatus, FailureReason
from scalemyprints.domain.design.ports import DesignJobStore

if TYPE_CHECKING:
    from scalemyprints.domain.design.models import DesignArtifact, DesignJob


class MemoryDesignJobStore(DesignJobStore):
    """Process-local job store."""

    def __init__(self) -> None:
        self._jobs: dict[str, DesignJob] = {}
        self._lock = asyncio.Lock()

    async def create(self, job: DesignJob) -> None:
        async with self._lock:
            self._jobs[job.id] = job

    async def get(self, job_id: str, user_id: str) -> DesignJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.user_id != user_id:
                return None
            return job

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: DesignStatus | None = None,
    ) -> tuple[list[DesignJob], int]:
        async with self._lock:
            matching = [
                j
                for j in self._jobs.values()
                if j.user_id == user_id and (status is None or j.status == status)
            ]
        matching.sort(key=lambda j: j.created_at, reverse=True)
        total = len(matching)
        return matching[offset : offset + limit], total

    async def update_status(
        self,
        job_id: str,
        status: DesignStatus,
        *,
        enriched_prompt: str | None = None,
        artifacts: list[DesignArtifact] | None = None,
        failure_reason: FailureReason | None = None,
        failure_message: str | None = None,
        providers_attempted: list[str] | None = None,
        duration_ms: int | None = None,
        cost_usd_estimate: float | None = None,
    ) -> None:
        async with self._lock:
            existing = self._jobs.get(job_id)
            if existing is None:
                return
            now = datetime.now(UTC)
            self._jobs[job_id] = existing.model_copy(
                update={
                    "status": status,
                    "enriched_prompt": (
                        enriched_prompt if enriched_prompt is not None else existing.enriched_prompt
                    ),
                    "artifacts": (artifacts if artifacts is not None else existing.artifacts),
                    "failure_reason": (
                        failure_reason if failure_reason is not None else existing.failure_reason
                    ),
                    "failure_message": (
                        failure_message if failure_message is not None else existing.failure_message
                    ),
                    "providers_attempted": (
                        providers_attempted
                        if providers_attempted is not None
                        else existing.providers_attempted
                    ),
                    "duration_ms": (
                        duration_ms if duration_ms is not None else existing.duration_ms
                    ),
                    "cost_usd_estimate": (
                        cost_usd_estimate
                        if cost_usd_estimate is not None
                        else existing.cost_usd_estimate
                    ),
                    "updated_at": now,
                    "completed_at": (
                        now
                        if status in {DesignStatus.COMPLETED, DesignStatus.FAILED}
                        else existing.completed_at
                    ),
                }
            )

    async def soft_delete(self, job_id: str, user_id: str) -> bool:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.user_id != user_id:
                return False
            del self._jobs[job_id]
            return True
