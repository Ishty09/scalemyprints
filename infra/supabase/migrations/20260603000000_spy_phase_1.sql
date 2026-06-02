-- =============================================================================
-- ScaleMyPrints Spy — Phase 1 schema
-- =============================================================================
-- Adds:
--   • spy_listings              canonical cross-marketplace listing rows
--   • spy_listing_snapshots     timeseries for velocity / spike detection
--   • spy_shops                 cached shop profiles
--   • spy_design_embeddings     pgvector + pHash for reverse image search
--   • spy_design_listing_links  many-to-many between embeddings and listings
--   • spy_viral_signals         placeholder for Phase 3 viral mining
--   • spy_jobs                  async job envelope (reverse-image, shop-audit)
--   • RPCs: spy_search_phash, spy_search_clip
--
-- All public-data tables have RLS enabled. Listings + shops + signals are
-- world-readable to authenticated users (they're public marketplace data).
-- Embeddings and jobs are tighter — jobs are per-user.
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 0. Extensions
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector for CLIP search


-- ---------------------------------------------------------------------------
-- 1. spy_listings — canonical listing rows
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_listings (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  marketplace          text          NOT NULL,
  external_id          text          NOT NULL,
  url                  text          NOT NULL,
  title                text          NOT NULL,
  description          text,
  tags                 text[]        NOT NULL DEFAULT ARRAY[]::text[],
  price_usd            numeric(10, 2),
  currency             text,
  thumbnail_url        text,
  image_urls           text[]        NOT NULL DEFAULT ARRAY[]::text[],
  shop_external_id     text,
  shop_handle          text,
  shop_url             text,
  status               text          NOT NULL DEFAULT 'active',
  favorites            integer,
  reviews_count        integer,
  rating               numeric(3, 2),
  est_daily_sales      numeric(10, 3),
  velocity_class       text          NOT NULL DEFAULT 'steady',
  first_seen_at        timestamptz   NOT NULL DEFAULT now(),
  last_seen_at         timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_listings_marketplace_check CHECK (marketplace IN (
    'etsy', 'amazon_merch', 'redbubble', 'teepublic',
    'society6', 'zazzle', 'spreadshirt', 'bonanza'
  )),
  CONSTRAINT spy_listings_status_check CHECK (status IN (
    'active', 'sold_out', 'inactive', 'delisted', 'unknown'
  )),
  CONSTRAINT spy_listings_velocity_check CHECK (velocity_class IN (
    'dormant', 'steady', 'rising', 'spiking', 'explosive'
  )),
  CONSTRAINT spy_listings_external_unique UNIQUE (marketplace, external_id)
);

CREATE INDEX IF NOT EXISTS idx_spy_listings_marketplace_last_seen
  ON public.spy_listings (marketplace, last_seen_at DESC);

CREATE INDEX IF NOT EXISTS idx_spy_listings_shop
  ON public.spy_listings (marketplace, shop_handle)
  WHERE shop_handle IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_spy_listings_velocity
  ON public.spy_listings (velocity_class, last_seen_at DESC)
  WHERE velocity_class IN ('rising', 'spiking', 'explosive');

CREATE INDEX IF NOT EXISTS idx_spy_listings_title_trgm
  ON public.spy_listings USING gin (title gin_trgm_ops);

-- pg_trgm needs to exist for the trigram index above
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

ALTER TABLE public.spy_listings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_listings_read_all ON public.spy_listings;
CREATE POLICY spy_listings_read_all ON public.spy_listings
  FOR SELECT TO authenticated USING (true);

COMMENT ON TABLE public.spy_listings IS
  'Canonical cross-platform POD listings tracked by Spy.';


-- ---------------------------------------------------------------------------
-- 2. spy_listing_snapshots — timeseries for velocity / spike detection
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_listing_snapshots (
  id                   bigserial     PRIMARY KEY,
  listing_id           uuid          NOT NULL REFERENCES public.spy_listings(id) ON DELETE CASCADE,
  captured_at          timestamptz   NOT NULL DEFAULT now(),
  price_usd            numeric(10, 2),
  favorites            integer,
  reviews_count        integer,
  rating               numeric(3, 2),
  est_daily_sales      numeric(10, 3),
  rank_within_query    integer,
  raw_payload          jsonb
);

CREATE INDEX IF NOT EXISTS idx_spy_snapshots_listing_captured
  ON public.spy_listing_snapshots (listing_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_spy_snapshots_captured
  ON public.spy_listing_snapshots (captured_at DESC);

ALTER TABLE public.spy_listing_snapshots ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_snapshots_read_all ON public.spy_listing_snapshots;
CREATE POLICY spy_snapshots_read_all ON public.spy_listing_snapshots
  FOR SELECT TO authenticated USING (true);

COMMENT ON TABLE public.spy_listing_snapshots IS
  'Per-listing timeseries of price/favorites/reviews/sales for velocity analysis.';


-- ---------------------------------------------------------------------------
-- 3. spy_shops — cached shop profiles
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_shops (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  marketplace          text          NOT NULL,
  external_id          text          NOT NULL,
  handle               text          NOT NULL,
  display_name         text,
  url                  text          NOT NULL,
  location             text,
  joined_year          integer,
  total_sales          bigint,
  listings_count       integer,
  avg_review_rating    numeric(3, 2),
  reviews_count        integer,
  first_seen_at        timestamptz   NOT NULL DEFAULT now(),
  last_seen_at         timestamptz   NOT NULL DEFAULT now(),

  CONSTRAINT spy_shops_marketplace_check CHECK (marketplace IN (
    'etsy', 'amazon_merch', 'redbubble', 'teepublic',
    'society6', 'zazzle', 'spreadshirt', 'bonanza'
  )),
  CONSTRAINT spy_shops_external_unique UNIQUE (marketplace, external_id)
);

CREATE INDEX IF NOT EXISTS idx_spy_shops_handle
  ON public.spy_shops (marketplace, handle);

ALTER TABLE public.spy_shops ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_shops_read_all ON public.spy_shops;
CREATE POLICY spy_shops_read_all ON public.spy_shops
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 4. spy_design_embeddings — pgvector for CLIP + bigint for pHash
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_design_embeddings (
  sha256          text          PRIMARY KEY,
  phash           bigint        NOT NULL,
  clip_embedding  vector(512)   NOT NULL,
  width           integer       NOT NULL,
  height          integer       NOT NULL,
  bytes_size      integer       NOT NULL,
  source_url      text,
  created_at      timestamptz   NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_spy_embeddings_phash
  ON public.spy_design_embeddings (phash);

-- IVFFlat index over CLIP vectors (cosine ops).
-- `lists` ≈ sqrt(rows). 100 is a reasonable starting point.
CREATE INDEX IF NOT EXISTS idx_spy_embeddings_clip_ivfflat
  ON public.spy_design_embeddings
  USING ivfflat (clip_embedding vector_cosine_ops)
  WITH (lists = 100);

ALTER TABLE public.spy_design_embeddings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_embeddings_read_all ON public.spy_design_embeddings;
CREATE POLICY spy_embeddings_read_all ON public.spy_design_embeddings
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 5. spy_design_listing_links — N:M between embeddings and listings
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_design_listing_links (
  sha256          text          NOT NULL REFERENCES public.spy_design_embeddings(sha256) ON DELETE CASCADE,
  listing_id      uuid          NOT NULL REFERENCES public.spy_listings(id) ON DELETE CASCADE,
  created_at      timestamptz   NOT NULL DEFAULT now(),
  PRIMARY KEY (sha256, listing_id)
);

CREATE INDEX IF NOT EXISTS idx_spy_links_listing
  ON public.spy_design_listing_links (listing_id);

ALTER TABLE public.spy_design_listing_links ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_links_read_all ON public.spy_design_listing_links;
CREATE POLICY spy_links_read_all ON public.spy_design_listing_links
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 6. spy_viral_signals — Phase 3 placeholder (trending phrases / memes)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_viral_signals (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  source               text          NOT NULL,
  source_url           text,
  phrase               text          NOT NULL,
  detected_at          timestamptz   NOT NULL DEFAULT now(),
  engagement           bigint        NOT NULL DEFAULT 0,
  momentum_score       integer       NOT NULL DEFAULT 0,
  pod_readiness_score  integer       NOT NULL DEFAULT 0,
  existing_pod_count   integer       NOT NULL DEFAULT 0,
  suggested_styles     text[]        NOT NULL DEFAULT ARRAY[]::text[],
  note                 text,

  CONSTRAINT spy_viral_source_check CHECK (source IN (
    'reddit', 'tiktok', 'twitter', 'instagram', 'pinterest',
    'youtube_shorts', 'google_trends'
  )),
  CONSTRAINT spy_viral_momentum_check CHECK (momentum_score BETWEEN 0 AND 100),
  CONSTRAINT spy_viral_readiness_check CHECK (pod_readiness_score BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS idx_spy_viral_detected
  ON public.spy_viral_signals (detected_at DESC);

ALTER TABLE public.spy_viral_signals ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_viral_read_all ON public.spy_viral_signals;
CREATE POLICY spy_viral_read_all ON public.spy_viral_signals
  FOR SELECT TO authenticated USING (true);


-- ---------------------------------------------------------------------------
-- 7. spy_jobs — async job envelope (reverse-image, shop-audit, viral-scan)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.spy_jobs (
  id                   uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              uuid          NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  kind                 text          NOT NULL,
  status               text          NOT NULL DEFAULT 'queued',
  request_payload      jsonb         NOT NULL,
  result_payload       jsonb,
  failure_reason       text,
  failure_message      text,
  sources_attempted    text[]        NOT NULL DEFAULT ARRAY[]::text[],
  sources_succeeded    text[]        NOT NULL DEFAULT ARRAY[]::text[],
  duration_ms          integer       NOT NULL DEFAULT 0,
  created_at           timestamptz   NOT NULL DEFAULT now(),
  updated_at           timestamptz   NOT NULL DEFAULT now(),
  completed_at         timestamptz,

  CONSTRAINT spy_jobs_kind_check CHECK (kind IN (
    'reverse_image', 'shop_audit', 'viral_scan', 'velocity_recompute'
  )),
  CONSTRAINT spy_jobs_status_check CHECK (status IN (
    'queued', 'running', 'completed', 'partial', 'failed', 'cancelled'
  )),
  CONSTRAINT spy_jobs_failure_check CHECK (failure_reason IS NULL OR failure_reason IN (
    'quota_exceeded', 'source_blocked', 'source_rate_limited',
    'invalid_input', 'unsupported_marketplace',
    'image_too_large', 'image_invalid',
    'embedding_failed', 'storage_failure', 'internal'
  ))
);

CREATE INDEX IF NOT EXISTS idx_spy_jobs_user_created
  ON public.spy_jobs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_spy_jobs_status
  ON public.spy_jobs (status)
  WHERE status IN ('queued', 'running');

ALTER TABLE public.spy_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS spy_jobs_select_own ON public.spy_jobs;
CREATE POLICY spy_jobs_select_own ON public.spy_jobs
  FOR SELECT USING (auth.uid() = user_id);


-- ---------------------------------------------------------------------------
-- 8. RPC — pHash Hamming-distance search
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.spy_search_phash(
  target_hash bigint,
  max_distance integer DEFAULT 12,
  lim integer DEFAULT 50
)
RETURNS TABLE (
  sha256       text,
  listing_ids  uuid[],
  distance     integer
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH dist AS (
    SELECT
      e.sha256,
      length(replace((e.phash # target_hash)::bit(64)::text, '0', ''))::int AS d
    FROM public.spy_design_embeddings e
  ),
  filtered AS (
    SELECT * FROM dist WHERE d <= max_distance ORDER BY d ASC LIMIT lim
  )
  SELECT
    f.sha256,
    COALESCE(
      ARRAY_AGG(l.listing_id) FILTER (WHERE l.listing_id IS NOT NULL),
      ARRAY[]::uuid[]
    ) AS listing_ids,
    f.d AS distance
  FROM filtered f
  LEFT JOIN public.spy_design_listing_links l ON l.sha256 = f.sha256
  GROUP BY f.sha256, f.d
  ORDER BY f.d ASC;
$$;

REVOKE ALL ON FUNCTION public.spy_search_phash(bigint, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.spy_search_phash(bigint, integer, integer) TO authenticated, service_role;


-- ---------------------------------------------------------------------------
-- 9. RPC — CLIP cosine-similarity search
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.spy_search_clip(
  query vector(512),
  min_cosine double precision DEFAULT 0.70,
  lim integer DEFAULT 50
)
RETURNS TABLE (
  sha256       text,
  listing_ids  uuid[],
  cosine       double precision
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  WITH sim AS (
    SELECT
      e.sha256,
      (1.0 - (e.clip_embedding <=> query)) AS cosine
    FROM public.spy_design_embeddings e
  ),
  filtered AS (
    SELECT * FROM sim WHERE cosine >= min_cosine ORDER BY cosine DESC LIMIT lim
  )
  SELECT
    f.sha256,
    COALESCE(
      ARRAY_AGG(l.listing_id) FILTER (WHERE l.listing_id IS NOT NULL),
      ARRAY[]::uuid[]
    ) AS listing_ids,
    f.cosine
  FROM filtered f
  LEFT JOIN public.spy_design_listing_links l ON l.sha256 = f.sha256
  GROUP BY f.sha256, f.cosine
  ORDER BY f.cosine DESC;
$$;

REVOKE ALL ON FUNCTION public.spy_search_clip(vector, double precision, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.spy_search_clip(vector, double precision, integer) TO authenticated, service_role;


-- ---------------------------------------------------------------------------
-- 10. Convenience view — hot movers feed
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW public.spy_hot_movers AS
SELECT
  l.id,
  l.marketplace,
  l.title,
  l.url,
  l.thumbnail_url,
  l.shop_handle,
  l.shop_url,
  l.velocity_class,
  l.est_daily_sales,
  l.price_usd,
  l.favorites,
  l.reviews_count,
  l.last_seen_at
FROM public.spy_listings l
WHERE l.velocity_class IN ('rising', 'spiking', 'explosive')
  AND l.last_seen_at > now() - INTERVAL '7 days';

COMMENT ON VIEW public.spy_hot_movers IS
  'Listings flagged as rising/spiking/explosive within the last 7 days.';
