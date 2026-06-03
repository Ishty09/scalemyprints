-- =============================================================================
-- ScaleMyPrints Spy — Phase 4 schema additions
-- =============================================================================
-- Adds:
--   • spy_watchlists           per-user watchlists for phrases/shops/listings
--   • spy_alerts               generated alert events (in-app feed source)
--   • spy_api_keys             user-owned API keys for webhook/programmatic access
--   • spy_shop_audit_history   compacted history per (marketplace, handle)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. spy_watchlists
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_watchlists (
  id            uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  watch_type    text          NOT NULL,
  target        text          NOT NULL,
  label         text,
  triggers      text[]        NOT NULL DEFAULT ARRAY[]::text[],
  channels      jsonb         NOT NULL DEFAULT '[]'::jsonb,
  enabled       boolean       NOT NULL DEFAULT true,
  created_at    timestamptz   NOT NULL DEFAULT now(),
  updated_at    timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_watchlists_type_check CHECK (watch_type IN (
    'phrase', 'shop', 'listing', 'viral_category'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_watchlists_user
  ON public.spy_watchlists (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_spy_watchlists_target
  ON public.spy_watchlists (watch_type, target)
  WHERE enabled = true;

ALTER TABLE public.spy_watchlists ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_watchlists_select_own ON public.spy_watchlists;
CREATE POLICY spy_watchlists_select_own ON public.spy_watchlists
  FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_watchlists_insert_own ON public.spy_watchlists;
CREATE POLICY spy_watchlists_insert_own ON public.spy_watchlists
  FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_watchlists_update_own ON public.spy_watchlists;
CREATE POLICY spy_watchlists_update_own ON public.spy_watchlists
  FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_watchlists_delete_own ON public.spy_watchlists;
CREATE POLICY spy_watchlists_delete_own ON public.spy_watchlists
  FOR DELETE USING (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 2. spy_alerts
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_alerts (
  id                       uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                  uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  watchlist_id             uuid          REFERENCES public.spy_watchlists(id) ON DELETE SET NULL,
  trigger                  text          NOT NULL,
  status                   text          NOT NULL DEFAULT 'pending',
  headline                 text          NOT NULL,
  detail                   text,
  payload                  jsonb         NOT NULL DEFAULT '{}'::jsonb,
  target_url               text,
  channels_attempted       text[]        NOT NULL DEFAULT ARRAY[]::text[],
  channels_delivered       text[]        NOT NULL DEFAULT ARRAY[]::text[],
  severity                 integer       NOT NULL DEFAULT 50 CHECK (severity BETWEEN 0 AND 100),
  created_at               timestamptz   NOT NULL DEFAULT now(),
  delivered_at             timestamptz,
  read_at                  timestamptz,

  CONSTRAINT spy_alerts_trigger_check CHECK (trigger IN (
    'velocity_spike', 'new_listing', 'price_drop', 'price_increase',
    'viral_hit', 'saturation_drop'
  )),
  CONSTRAINT spy_alerts_status_check CHECK (status IN (
    'pending', 'delivered', 'read', 'dismissed', 'failed'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_alerts_user_created
  ON public.spy_alerts (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_spy_alerts_user_unread
  ON public.spy_alerts (user_id, created_at DESC)
  WHERE status NOT IN ('read', 'dismissed');

ALTER TABLE public.spy_alerts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_alerts_select_own ON public.spy_alerts;
CREATE POLICY spy_alerts_select_own ON public.spy_alerts
  FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_alerts_update_own ON public.spy_alerts;
CREATE POLICY spy_alerts_update_own ON public.spy_alerts
  FOR UPDATE USING (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 3. spy_api_keys
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_api_keys (
  id            uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  label         text          NOT NULL,
  prefix        text          NOT NULL,
  key_hash      text          NOT NULL UNIQUE,
  scopes        text[]        NOT NULL DEFAULT ARRAY['spy:read']::text[],
  last_used_at  timestamptz,
  revoked       boolean       NOT NULL DEFAULT false,
  created_at    timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spy_api_keys_user
  ON public.spy_api_keys (user_id, created_at DESC);

ALTER TABLE public.spy_api_keys ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_api_keys_select_own ON public.spy_api_keys;
CREATE POLICY spy_api_keys_select_own ON public.spy_api_keys
  FOR SELECT USING (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_api_keys_insert_own ON public.spy_api_keys;
CREATE POLICY spy_api_keys_insert_own ON public.spy_api_keys
  FOR INSERT WITH CHECK (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_api_keys_update_own ON public.spy_api_keys;
CREATE POLICY spy_api_keys_update_own ON public.spy_api_keys
  FOR UPDATE USING (auth.uid() = user_id);
DROP POLICY IF EXISTS spy_api_keys_delete_own ON public.spy_api_keys;
CREATE POLICY spy_api_keys_delete_own ON public.spy_api_keys
  FOR DELETE USING (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 4. spy_shop_audit_history — timeseries of shop audits for diff tracking
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_shop_audit_history (
  id                      bigserial     PRIMARY KEY,
  marketplace             text          NOT NULL,
  handle                  text          NOT NULL,
  audit_payload           jsonb         NOT NULL,
  est_monthly_revenue_usd numeric(12, 2),
  listings_sampled        integer       NOT NULL DEFAULT 0,
  captured_at             timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_shop_audit_history_marketplace_check CHECK (marketplace IN (
    'etsy', 'amazon_merch', 'redbubble', 'teepublic',
    'society6', 'zazzle', 'spreadshirt', 'bonanza'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_shop_audit_history_handle
  ON public.spy_shop_audit_history (marketplace, handle, captured_at DESC);

ALTER TABLE public.spy_shop_audit_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_shop_audit_history_read_all ON public.spy_shop_audit_history;
CREATE POLICY spy_shop_audit_history_read_all ON public.spy_shop_audit_history
  FOR SELECT TO authenticated USING (true);
