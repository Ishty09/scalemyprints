-- =============================================================================
-- ScaleMyPrints Spy — Phase 2 schema additions
-- =============================================================================
-- Adds:
--   • spy_ad_hits              FB/IG/TikTok ad-library observations
--   • spy_shop_audits          cached shop teardown reports
--   • spy_saturation_cache     per-phrase saturation scores (cache)
--
-- Phase 2 also lights up the cron that writes to spy_listing_snapshots and
-- updates spy_listings.velocity_class.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 1. spy_ad_hits — ad-library observations
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_ad_hits (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  platform             text          NOT NULL,
  ad_id                text          NOT NULL,
  page_or_handle       text          NOT NULL,
  page_id              text,
  ad_creative_url      text,
  landing_url          text,
  primary_text         text,
  headline             text,
  cta                  text,
  started_at           timestamptz,
  last_seen_at         timestamptz,
  impressions_lower    bigint,
  impressions_upper    bigint,
  spend_usd_lower      numeric(10, 2),
  spend_usd_upper      numeric(10, 2),
  countries            text[]        NOT NULL DEFAULT ARRAY[]::text[],
  associated_listing_id uuid         REFERENCES public.spy_listings(id) ON DELETE SET NULL,
  captured_at          timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_ad_hits_platform_check CHECK (platform IN (
    'facebook', 'instagram', 'tiktok', 'pinterest', 'google_ads'
  )),
  CONSTRAINT spy_ad_hits_unique UNIQUE (platform, ad_id)
);

CREATE INDEX IF NOT EXISTS idx_spy_ad_hits_page
  ON public.spy_ad_hits (platform, page_or_handle);

CREATE INDEX IF NOT EXISTS idx_spy_ad_hits_listing
  ON public.spy_ad_hits (associated_listing_id)
  WHERE associated_listing_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_spy_ad_hits_captured
  ON public.spy_ad_hits (captured_at DESC);

ALTER TABLE public.spy_ad_hits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_ad_hits_read_all ON public.spy_ad_hits;
CREATE POLICY spy_ad_hits_read_all ON public.spy_ad_hits
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 2. spy_shop_audits — cached shop teardown reports
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_shop_audits (
  id                       uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  marketplace              text          NOT NULL,
  handle                   text          NOT NULL,
  depth                    text          NOT NULL,
  listings_sampled         integer       NOT NULL DEFAULT 0,
  est_monthly_revenue_usd  numeric(12, 2),
  avg_price_usd            numeric(10, 2),
  new_listings_last_30d    integer,
  restock_cadence_days     numeric(8, 2),
  most_used_tags           jsonb         NOT NULL DEFAULT '[]'::jsonb,
  report_payload           jsonb         NOT NULL DEFAULT '{}'::jsonb,
  captured_at              timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_shop_audits_marketplace_check CHECK (marketplace IN (
    'etsy', 'amazon_merch', 'redbubble', 'teepublic',
    'society6', 'zazzle', 'spreadshirt', 'bonanza'
  )),
  CONSTRAINT spy_shop_audits_depth_check CHECK (depth IN (
    'shallow', 'standard', 'deep'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_shop_audits_handle
  ON public.spy_shop_audits (marketplace, handle, captured_at DESC);

ALTER TABLE public.spy_shop_audits ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_shop_audits_read_all ON public.spy_shop_audits;
CREATE POLICY spy_shop_audits_read_all ON public.spy_shop_audits
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 3. spy_saturation_cache — per-phrase saturation score cache
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_saturation_cache (
  phrase_normalized        text          PRIMARY KEY,
  score                    integer       NOT NULL CHECK (score BETWEEN 0 AND 100),
  saturation_class         text          NOT NULL,
  listings_count           integer       NOT NULL,
  unique_shops             integer       NOT NULL,
  hhi                      numeric(6, 4) NOT NULL,
  gmv_pool_usd             numeric(14, 2) NOT NULL DEFAULT 0,
  density_component        integer       NOT NULL,
  concentration_component  integer       NOT NULL,
  velocity_component       integer       NOT NULL,
  recency_component        integer       NOT NULL,
  explanation              text,
  computed_at              timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_saturation_class_check CHECK (saturation_class IN (
    'open', 'mild', 'crowded', 'saturated'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_saturation_computed
  ON public.spy_saturation_cache (computed_at DESC);

ALTER TABLE public.spy_saturation_cache ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_saturation_read_all ON public.spy_saturation_cache;
CREATE POLICY spy_saturation_read_all ON public.spy_saturation_cache
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 4. View — joined view for the front-end "hot movers + ads" panel
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.spy_hot_movers_with_ads AS
SELECT
  hm.*,
  COALESCE(ad_count.n, 0) AS active_ads_count
FROM public.spy_hot_movers hm
LEFT JOIN LATERAL (
  SELECT count(*) AS n
  FROM public.spy_ad_hits ah
  WHERE ah.associated_listing_id = hm.id
    AND (ah.last_seen_at IS NULL OR ah.last_seen_at > now() - INTERVAL '30 days')
) ad_count ON true;
