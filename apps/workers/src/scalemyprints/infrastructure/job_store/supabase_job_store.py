"""
Supabase DesignJobStore.

Persists DesignJob to the `design_jobs` table (see migration
0001_design_engine.sql). Uses the supabase-py sync client wrapped in
run_in_executor to keep the orchestrator async.

Schema (see migration):
  design_jobs (
    id uuid pk,
    user_id uuid fk auth.users,
    status text,
    request jsonb,
    enriched_prompt text,
    artifacts jsonb,
    failure_reason text,
    failure_message text,
    providers_attempted jsonb,
    plan_at_creation text,
    quota_consumed int,
    cost_usd_estimate numeric,
    duration_ms int,
    parent_job_id uuid,
    revision int,
    created_at timestamptz,
    updated_at timestamptz,
    completed_at timestamptz,
    deleted_at timestamptz
  )
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from functools import partial
from typing import Any

from postgrest.types import CountMethod
from supabase import Client, create_client

from scalemyprints.core.logging import get_logger
from scalemyprints.domain.design.enums import (
    DesignStatus,
    FailureReason,
)
from scalemyprints.domain.design.models import (
    DesignArtifact,
    DesignJob,
    DesignRequest,
)
from scalemyprints.domain.design.ports import DesignJobStore

logger = get_logger(__name__)

TABLE = "design_jobs"


class SupabaseDesignJobStore(DesignJobStore):
    """Supabase Postgres-backed job store."""

    def __init__(
        self,
        *,
        supabase_url: str,
        service_role_key: str,
    ) -> None:
        if not supabase_url or not service_role_key:
            raise ValueError("supabase_url + service_role_key required")
        self._client: Client = create_client(supabase_url, service_role_key)

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def create(self, job: DesignJob) -> None:
        row = _job_to_row(job)
        await self._run(partial(self._client.table(TABLE).insert(row).execute))

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
        now = datetime.now(UTC)
        update: dict[str, Any] = {
            "status": status.value,
            "updated_at": now.isoformat(),
        }
        if enriched_prompt is not None:
            update["enriched_prompt"] = enriched_prompt
        if artifacts is not None:
            update["artifacts"] = [a.model_dump(mode="json") for a in artifacts]
        if failure_reason is not None:
            update["failure_reason"] = failure_reason.value
        if failure_message is not None:
            update["failure_message"] = failure_message
        if providers_attempted is not None:
            update["providers_attempted"] = providers_attempted
        if duration_ms is not None:
            update["duration_ms"] = duration_ms
        if cost_usd_estimate is not None:
            update["cost_usd_estimate"] = cost_usd_estimate
        if status in {DesignStatus.COMPLETED, DesignStatus.FAILED, DesignStatus.CANCELLED}:
            update["completed_at"] = now.isoformat()

        await self._run(partial(self._client.table(TABLE).update(update).eq("id", job_id).execute))

    async def soft_delete(self, job_id: str, user_id: str) -> bool:
        now = datetime.now(UTC).isoformat()
        result = await self._run(
            partial(
                self._client.table(TABLE)
                .update({"deleted_at": now})
                .eq("id", job_id)
                .eq("user_id", user_id)
                .is_("deleted_at", "null")
                .execute
            )
        )
        rows = getattr(result, "data", None) or []
        return bool(rows)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get(self, job_id: str, user_id: str) -> DesignJob | None:
        result = await self._run(
            partial(
                self._client.table(TABLE)
                .select("*")
                .eq("id", job_id)
                .eq("user_id", user_id)
                .is_("deleted_at", "null")
                .single()
                .execute
            )
        )
        row = getattr(result, "data", None)
        if not row:
            return None
        return _row_to_job(row)

    async def list_for_user(
        self,
        user_id: str,
        *,
        limit: int = 20,
        offset: int = 0,
        status: DesignStatus | None = None,
    ) -> tuple[list[DesignJob], int]:
        def _build_query() -> Any:
            q = (
                self._client.table(TABLE)
                .select("*", count=CountMethod.exact)
                .eq("user_id", user_id)
                .is_("deleted_at", "null")
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
            )
            if status is not None:
                q = q.eq("status", status.value)
            return q.execute()

        result = await self._run(_build_query)
        rows = getattr(result, "data", None) or []
        total = getattr(result, "count", None) or len(rows)
        return [_row_to_job(r) for r in rows], int(total)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _run(call: Any) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, call)


# ---------------------------------------------------------------------------
# Mappers — Pydantic <-> Postgres row
# ---------------------------------------------------------------------------


def _job_to_row(job: DesignJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "user_id": job.user_id,
        "status": job.status.value,
        "request": job.request.model_dump(mode="json"),
        "enriched_prompt": job.enriched_prompt,
        "artifacts": [a.model_dump(mode="json") for a in job.artifacts],
        "failure_reason": job.failure_reason.value if job.failure_reason else None,
        "failure_message": job.failure_message,
        "providers_attempted": job.providers_attempted,
        "plan_at_creation": job.plan_at_creation,
        "quota_consumed": job.quota_consumed,
        "cost_usd_estimate": job.cost_usd_estimate,
        "duration_ms": job.duration_ms,
        "parent_job_id": job.parent_job_id,
        "revision": job.revision,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _row_to_job(row: dict[str, Any]) -> DesignJob:
    request_payload = row.get("request") or {}
    artifacts = [DesignArtifact.model_validate(a) for a in (row.get("artifacts") or [])]
    failure_reason_raw = row.get("failure_reason")
    return DesignJob(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        request=DesignRequest.model_validate(request_payload),
        status=DesignStatus(row["status"]),
        enriched_prompt=row.get("enriched_prompt"),
        artifacts=artifacts,
        failure_reason=FailureReason(failure_reason_raw) if failure_reason_raw else None,
        failure_message=row.get("failure_message"),
        providers_attempted=list(row.get("providers_attempted") or []),
        plan_at_creation=row.get("plan_at_creation"),
        quota_consumed=int(row.get("quota_consumed") or 0),
        cost_usd_estimate=row.get("cost_usd_estimate"),
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
        completed_at=_parse_dt(row["completed_at"]) if row.get("completed_at") else None,
        duration_ms=int(row.get("duration_ms") or 0),
        parent_job_id=row.get("parent_job_id"),
        revision=int(row.get("revision") or 0),
    )


def _parse_dt(value: str) -> datetime:
    """Postgres timestamptz → aware datetime."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)
