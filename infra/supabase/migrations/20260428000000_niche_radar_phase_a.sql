-- =============================================================================
-- Niche Radar — Phase A schema
-- =============================================================================
-- Adds tables for niche search history and saved monitors.
-- Mirrors the pattern from initial trademark migration:
--   * RLS enabled
--   * Per-user policies enforced via auth.uid()
--   * Indexes on common query paths
-- =============================================================================

-- 1. niche_searches — history of searches (per user)
CREATE TABLE IF NOT EXISTS public.niche_searches (
  id           uuid           PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid           NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  keyword      text           NOT NULL,
  country      text           NOT NULL,
  nhs_score    integer        NOT NULL CHECK (nhs_score BETWEEN 0 AND 100),
  health       text           NOT NULL,
  full_result  jsonb          NOT NULL,
  searched_at  timestamptz    NOT NULL DEFAULT now(),

  CONSTRAINT niche_searches_country_check
    CHECK (country IN ('US', 'UK', 'AU', 'CA', 'DE')),
  CONSTRAINT niche_searches_health_check
    CHECK (health IN ('hot', 'promising', 'moderate', 'weak', 'avoid'))
);

CREATE INDEX IF NOT EXISTS idx_niche_searches_user_searched
  ON public.niche_searches (user_id, searched_at DESC);

CREATE INDEX IF NOT EXISTS idx_niche_searches_keyword
  ON public.niche_searches (lower(keyword));

ALTER TABLE public.niche_searches ENABLE ROW LEVEL SECURITY;

CREATE POLICY niche_searches_select_own ON public.niche_searches
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY niche_searches_insert_own ON public.niche_searches
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY niche_searches_delete_own ON public.niche_searches
  FOR DELETE USING (auth.uid() = user_id);

COMMENT ON TABLE public.niche_searches IS
  'Per-user history of niche analyses. Phase A: stores last 50 per user.';


-- 2. niche_monitors — saved niches user wants to track over time
CREATE TABLE IF NOT EXISTS public.niche_monitors (
  id                       uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  niche_keyword            text          NOT NULL,
  country                  text          NOT NULL,
  last_score               integer       CHECK (last_score IS NULL OR (last_score BETWEEN 0 AND 100)),
  last_score_change        integer,                       -- delta vs previous check
  last_checked_at          timestamptz,
  notification_enabled     boolean       NOT NULL DEFAULT true,
  created_at               timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT niche_monitors_country_check
    CHECK (country IN ('US', 'UK', 'AU', 'CA', 'DE')),
  CONSTRAINT niche_monitors_unique_per_user
    UNIQUE (user_id, niche_keyword, country)
);

CREATE INDEX IF NOT EXISTS idx_niche_monitors_user
  ON public.niche_monitors (user_id, created_at DESC);

ALTER TABLE public.niche_monitors ENABLE ROW LEVEL SECURITY;

CREATE POLICY niche_monitors_select_own ON public.niche_monitors
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY niche_monitors_insert_own ON public.niche_monitors
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY niche_monitors_update_own ON public.niche_monitors
  FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY niche_monitors_delete_own ON public.niche_monitors
  FOR DELETE USING (auth.uid() = user_id);

COMMENT ON TABLE public.niche_monitors IS
  'User-saved niches monitored over time. Background cron refreshes scores (Phase B).';


-- 3. niche_events_cache — refresh-able cache for events lookups (optional)
CREATE TABLE IF NOT EXISTS public.niche_events_cache (
  id                     text          PRIMARY KEY,         -- e.g., "us-2026-05-10-mothers-day"
  country                text          NOT NULL,
  event_date             date          NOT NULL,
  event_name             text          NOT NULL,
  category               text          NOT NULL,
  description            text,
  pod_relevance_score    integer       NOT NULL CHECK (pod_relevance_score BETWEEN 0 AND 100),
  suggested_niches       text[]        NOT NULL DEFAULT '{}',
  refreshed_at           timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT niche_events_country_check
    CHECK (country IN ('US', 'UK', 'AU', 'CA', 'DE'))
);

CREATE INDEX IF NOT EXISTS idx_niche_events_country_date
  ON public.niche_events_cache (country, event_date);

CREATE INDEX IF NOT EXISTS idx_niche_events_relevance
  ON public.niche_events_cache (country, pod_relevance_score DESC);

-- Public-readable cache; writes restricted to service role
ALTER TABLE public.niche_events_cache ENABLE ROW LEVEL SECURITY;

CREATE POLICY niche_events_select_all ON public.niche_events_cache
  FOR SELECT USING (true);

COMMENT ON TABLE public.niche_events_cache IS
  'Optional DB-backed events cache. Phase A uses static JSON; Phase B can backfill here.';


-- =============================================================================
-- Helper view — recent searches with summary fields for dashboard
-- =============================================================================

CREATE OR REPLACE VIEW public.niche_recent_searches AS
SELECT
  s.id,
  s.user_id,
  s.keyword,
  s.country,
  s.nhs_score,
  s.health,
  s.searched_at,
  (s.full_result->>'duration_ms')::int           AS duration_ms,
  (s.full_result->'demand'->>'score')::int       AS demand_score,
  (s.full_result->'trend'->>'score')::int        AS trend_score,
  (s.full_result->'competition'->>'score')::int  AS competition_score
FROM public.niche_searches s;

COMMENT ON VIEW public.niche_recent_searches IS
  'Convenience view for dashboard recent-searches list with summary scores.';
