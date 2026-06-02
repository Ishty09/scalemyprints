-- =============================================================================
-- Design Engine — Phase A schema (idempotent / re-runnable)
-- =============================================================================
-- Adds:
--   • design_jobs       — persisted DesignJob lifecycle
--   • design_quota      — month-bucket usage counter per user
--   • user_plans        — plan slug per user (drives quota_for_plan)
--   • Storage bucket    — "designs" (private; signed URLs only)
--   • RPC               — increment_design_quota(user, bucket, n) (atomic upsert)
--
-- NOTE: The storage.objects RLS policy (per-user read access) is NOT
-- created here — Supabase requires that to be added via the Dashboard
-- (Storage → Policies → New policy on the "designs" bucket) because
-- storage.objects is owned by the supabase_storage_admin role and not
-- modifiable from the SQL editor. See README / PR description.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. user_plans — plan slug per user
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.user_plans (
  user_id      uuid          PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  plan         text          NOT NULL DEFAULT 'free',
  status       text          NOT NULL DEFAULT 'active',
  trial_ends_at timestamptz,
  updated_at   timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT user_plans_status_check
    CHECK (status IN ('active', 'trialing', 'past_due', 'cancelled', 'paused', 'expired')),
  CONSTRAINT user_plans_plan_check
    CHECK (plan IN (
      'free', 'starter', 'pro', 'agency',
      'core_bundle', 'pro_bundle', 'empire_bundle'
    ))
);

ALTER TABLE public.user_plans ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS user_plans_select_own ON public.user_plans;
CREATE POLICY user_plans_select_own ON public.user_plans
  FOR SELECT USING (auth.uid() = user_id);

COMMENT ON TABLE public.user_plans IS
  'Per-user plan slug. Updated by billing webhooks (Lemon Squeezy/Stripe).';


-- ---------------------------------------------------------------------------
-- 2. design_jobs — persisted DesignJob lifecycle
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.design_jobs (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  status               text          NOT NULL,

  -- Request payload (immutable after creation; full DesignRequest snapshot)
  request              jsonb         NOT NULL,

  -- Lifecycle output
  enriched_prompt      text,
  artifacts            jsonb         NOT NULL DEFAULT '[]'::jsonb,
  failure_reason       text,
  failure_message      text,
  providers_attempted  jsonb         NOT NULL DEFAULT '[]'::jsonb,

  -- Billing / observability
  plan_at_creation     text,
  quota_consumed       integer       NOT NULL DEFAULT 0,
  cost_usd_estimate    numeric(10, 4),
  duration_ms          integer       NOT NULL DEFAULT 0,

  -- Lineage
  parent_job_id        uuid          REFERENCES public.design_jobs(id) ON DELETE SET NULL,
  revision             integer       NOT NULL DEFAULT 0,

  -- Timestamps
  created_at           timestamptz   NOT NULL DEFAULT now(),
  updated_at           timestamptz   NOT NULL DEFAULT now(),
  completed_at         timestamptz,
  deleted_at           timestamptz,

  CONSTRAINT design_jobs_status_check CHECK (status IN (
    'queued', 'enriching', 'generating', 'post_processing',
    'completed', 'failed', 'cancelled'
  )),
  CONSTRAINT design_jobs_failure_reason_check CHECK (failure_reason IS NULL OR failure_reason IN (
    'quota_exceeded', 'provider_unavailable', 'provider_rate_limited',
    'policy_violation', 'invalid_prompt', 'storage_failure', 'internal'
  ))
);

CREATE INDEX IF NOT EXISTS idx_design_jobs_user_created
  ON public.design_jobs (user_id, created_at DESC)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_design_jobs_status
  ON public.design_jobs (status)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_design_jobs_parent
  ON public.design_jobs (parent_job_id)
  WHERE parent_job_id IS NOT NULL;

ALTER TABLE public.design_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_jobs_select_own ON public.design_jobs;
CREATE POLICY design_jobs_select_own ON public.design_jobs
  FOR SELECT USING (auth.uid() = user_id AND deleted_at IS NULL);

DROP POLICY IF EXISTS design_jobs_insert_own ON public.design_jobs;
CREATE POLICY design_jobs_insert_own ON public.design_jobs
  FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS design_jobs_update_own ON public.design_jobs;
CREATE POLICY design_jobs_update_own ON public.design_jobs
  FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS design_jobs_delete_own ON public.design_jobs;
CREATE POLICY design_jobs_delete_own ON public.design_jobs
  FOR DELETE USING (auth.uid() = user_id);

COMMENT ON TABLE public.design_jobs IS
  'Persisted DesignJob lifecycle. Soft-deleted via deleted_at; rows kept for billing audit.';


-- ---------------------------------------------------------------------------
-- 3. design_quota — month-bucket counter per user
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.design_quota (
  user_id       uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  month_bucket  text          NOT NULL,                        -- "YYYY-MM"
  used_count    integer       NOT NULL DEFAULT 0 CHECK (used_count >= 0),
  updated_at    timestamptz   NOT NULL DEFAULT now(),

  PRIMARY KEY (user_id, month_bucket),
  CONSTRAINT design_quota_month_format CHECK (month_bucket ~ '^[0-9]{4}-[0-9]{2}$')
);

CREATE INDEX IF NOT EXISTS idx_design_quota_user
  ON public.design_quota (user_id);

ALTER TABLE public.design_quota ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS design_quota_select_own ON public.design_quota;
CREATE POLICY design_quota_select_own ON public.design_quota
  FOR SELECT USING (auth.uid() = user_id);

COMMENT ON TABLE public.design_quota IS
  'Monthly design generation count per user. Updated by increment_design_quota RPC.';


-- ---------------------------------------------------------------------------
-- 4. RPC — atomic upsert + increment
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.increment_design_quota(
  p_user_id      uuid,
  p_month_bucket text,
  p_increment    integer DEFAULT 1
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_new_count integer;
BEGIN
  IF p_increment <= 0 THEN
    RAISE EXCEPTION 'increment must be positive';
  END IF;

  INSERT INTO public.design_quota (user_id, month_bucket, used_count, updated_at)
  VALUES (p_user_id, p_month_bucket, p_increment, now())
  ON CONFLICT (user_id, month_bucket)
  DO UPDATE SET
    used_count = public.design_quota.used_count + EXCLUDED.used_count,
    updated_at = now()
  RETURNING used_count INTO v_new_count;

  RETURN v_new_count;
END;
$$;

REVOKE ALL ON FUNCTION public.increment_design_quota(uuid, text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.increment_design_quota(uuid, text, integer) TO service_role;

COMMENT ON FUNCTION public.increment_design_quota IS
  'Atomically upsert + increment month-bucket usage. Service-role only.';


-- ---------------------------------------------------------------------------
-- 5. Storage bucket — designs/{user_id}/{job_id}/{n}.png
-- ---------------------------------------------------------------------------
-- Created idempotently. Bucket is PRIVATE — access via signed URLs only.
-- The read-own RLS policy on storage.objects must be created via the
-- Supabase Dashboard (Storage → Policies → "designs" bucket), because
-- storage.objects is owned by supabase_storage_admin and can't be
-- modified from the SQL editor. Use this expression:
--
--   bucket_id = 'designs'
--   AND (auth.uid())::text = (storage.foldername(name))[1]
--
-- Operation: SELECT  •  Target roles: authenticated

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'designs',
  'designs',
  false,
  20 * 1024 * 1024,                                       -- 20 MB cap per file
  ARRAY['image/png', 'image/webp']
)
ON CONFLICT (id) DO NOTHING;


-- ---------------------------------------------------------------------------
-- 6. Convenience view — recent jobs with thumbnail + status
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.design_recent_jobs AS
SELECT
  j.id,
  j.user_id,
  j.status,
  j.request->>'prompt'                                         AS prompt,
  j.request->>'style'                                          AS style,
  j.request->>'aspect'                                         AS aspect,
  jsonb_array_length(j.artifacts)                              AS artifact_count,
  j.artifacts->0->>'thumbnail_url'                             AS thumbnail_url,
  j.failure_reason,
  j.created_at,
  j.completed_at,
  j.duration_ms
FROM public.design_jobs j
WHERE j.deleted_at IS NULL;

COMMENT ON VIEW public.design_recent_jobs IS
  'Convenience view for dashboard gallery: status + first thumbnail per job.';
