-- =============================================================================
-- ScaleMyPrints — Phase A initial schema
-- =============================================================================
-- Tables created:
--   waitlist            — pre-launch email collection
--   users_profile       — extends auth.users (auto-created via trigger)
--   subscriptions       — plan + tools entitlements (Lemon Squeezy in Phase D)
--   usage_limits        — per-user, per-tool quota tracking
--   tm_searches         — saved Trademark Shield searches (history)
--   tm_monitors         — ongoing trademark monitors
--   tm_alerts           — fired alerts from monitors
--   tm_cached_data      — server-side TTL cache (optional; in-memory works too)
--
-- This migration is idempotent for fresh projects. For incremental updates,
-- add new migrations rather than editing this one.
-- =============================================================================

-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- =============================================================================
-- Waitlist
-- =============================================================================

CREATE TABLE public.waitlist (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         TEXT UNIQUE NOT NULL,
    name          TEXT,
    source        TEXT,
    referrer      TEXT,
    interested_tools TEXT[],
    status        TEXT NOT NULL DEFAULT 'waiting'
                    CHECK (status IN ('waiting', 'invited', 'signed_up')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_waitlist_status_created ON public.waitlist(status, created_at);

-- Anonymous inserts allowed via service role from /api/waitlist
ALTER TABLE public.waitlist ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- User profile (extends auth.users)
-- =============================================================================

CREATE TABLE public.users_profile (
    id                    UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email                 TEXT UNIQUE NOT NULL,
    full_name             TEXT,
    avatar_url            TEXT,
    timezone              TEXT NOT NULL DEFAULT 'UTC',
    locale                TEXT NOT NULL DEFAULT 'en-US',
    is_founding_member    BOOLEAN NOT NULL DEFAULT false,
    onboarding_completed  BOOLEAN NOT NULL DEFAULT false,
    role                  TEXT NOT NULL DEFAULT 'user'
                              CHECK (role IN ('user', 'admin', 'agency_owner', 'agency_member')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE public.users_profile ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_profile_select_own"
    ON public.users_profile
    FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "users_profile_update_own"
    ON public.users_profile
    FOR UPDATE
    USING (auth.uid() = id);

-- =============================================================================
-- Subscriptions
-- =============================================================================

CREATE TABLE public.subscriptions (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id                  UUID NOT NULL REFERENCES public.users_profile(id) ON DELETE CASCADE,
    plan_tier                TEXT NOT NULL DEFAULT 'free'
                                CHECK (plan_tier IN (
                                    'free', 'starter', 'pro', 'agency', 'studio', 'scale',
                                    'core_bundle', 'pro_bundle', 'empire_bundle'
                                )),
    status                   TEXT NOT NULL DEFAULT 'active'
                                CHECK (status IN ('trialing', 'active', 'past_due', 'cancelled', 'paused', 'expired')),
    active_tools             JSONB NOT NULL DEFAULT '{"trademark_shield": true}'::jsonb,
    is_annual                BOOLEAN NOT NULL DEFAULT false,
    trial_ends_at            TIMESTAMPTZ,
    current_period_start     TIMESTAMPTZ,
    current_period_end       TIMESTAMPTZ,
    cancel_at_period_end     BOOLEAN NOT NULL DEFAULT false,
    -- Lemon Squeezy IDs (set in Phase D)
    lemonsqueezy_subscription_id TEXT,
    lemonsqueezy_customer_id     TEXT,
    metadata                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_subscriptions_user_active
    ON public.subscriptions(user_id)
    WHERE status IN ('trialing', 'active', 'past_due');

ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "subscriptions_select_own"
    ON public.subscriptions
    FOR SELECT
    USING (auth.uid() = user_id);

-- =============================================================================
-- Usage limits (per-user, per-tool, per-period)
-- =============================================================================

CREATE TABLE public.usage_limits (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id       UUID NOT NULL REFERENCES public.users_profile(id) ON DELETE CASCADE,
    tool          TEXT NOT NULL,
    limit_type    TEXT NOT NULL,
    limit_value   INTEGER NOT NULL,
    used_value    INTEGER NOT NULL DEFAULT 0,
    period_start  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    period_end    TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, tool, limit_type, period_start)
);

CREATE INDEX idx_usage_limits_user_tool
    ON public.usage_limits(user_id, tool, period_end DESC);

ALTER TABLE public.usage_limits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "usage_limits_select_own"
    ON public.usage_limits
    FOR SELECT
    USING (auth.uid() = user_id);

-- =============================================================================
-- Trademark Shield: searches
-- =============================================================================

CREATE TABLE public.tm_searches (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id            UUID NOT NULL REFERENCES public.users_profile(id) ON DELETE CASCADE,
    phrase             TEXT NOT NULL,
    jurisdictions      TEXT[] NOT NULL,
    nice_classes       INTEGER[] NOT NULL,
    overall_risk_score INTEGER NOT NULL CHECK (overall_risk_score BETWEEN 0 AND 100),
    overall_risk_level TEXT NOT NULL CHECK (overall_risk_level IN ('safe', 'low', 'medium', 'high', 'critical')),
    result             JSONB NOT NULL,
    analyzed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tm_searches_user_date ON public.tm_searches(user_id, analyzed_at DESC);
CREATE INDEX idx_tm_searches_phrase ON public.tm_searches(user_id, phrase);

ALTER TABLE public.tm_searches ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tm_searches_all_own"
    ON public.tm_searches
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- Trademark Shield: monitors
-- =============================================================================

CREATE TABLE public.tm_monitors (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id            UUID NOT NULL REFERENCES public.users_profile(id) ON DELETE CASCADE,
    phrase             TEXT NOT NULL,
    jurisdictions      TEXT[] NOT NULL,
    nice_classes       INTEGER[] NOT NULL,
    frequency          TEXT NOT NULL DEFAULT 'weekly'
                          CHECK (frequency IN ('daily', 'weekly', 'monthly')),
    alert_email        TEXT,
    alert_webhook_url  TEXT,
    is_active          BOOLEAN NOT NULL DEFAULT true,
    last_checked_at    TIMESTAMPTZ,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tm_monitors_user_active ON public.tm_monitors(user_id, is_active);
CREATE INDEX idx_tm_monitors_due ON public.tm_monitors(last_checked_at)
    WHERE is_active = true;

ALTER TABLE public.tm_monitors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tm_monitors_all_own"
    ON public.tm_monitors
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- Trademark Shield: alerts
-- =============================================================================

CREATE TABLE public.tm_alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    monitor_id      UUID NOT NULL REFERENCES public.tm_monitors(id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES public.users_profile(id) ON DELETE CASCADE,
    alert_type      TEXT NOT NULL CHECK (alert_type IN ('new_filing', 'status_change', 'high_risk')),
    payload         JSONB NOT NULL,
    sent_at         TIMESTAMPTZ,
    acknowledged_at TIMESTAMPTZ,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tm_alerts_user_unack ON public.tm_alerts(user_id)
    WHERE acknowledged_at IS NULL;

ALTER TABLE public.tm_alerts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "tm_alerts_select_own"
    ON public.tm_alerts
    FOR SELECT
    USING (auth.uid() = user_id);

-- =============================================================================
-- Trademark Shield: server-side TTL cache (optional; in-memory works for Phase A)
-- =============================================================================

CREATE TABLE public.tm_cached_data (
    cache_key   TEXT PRIMARY KEY,
    data        JSONB NOT NULL,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at  TIMESTAMPTZ NOT NULL
);

CREATE INDEX idx_tm_cached_expires ON public.tm_cached_data(expires_at);

-- Service role only — no RLS needed (no anon/authed access)
ALTER TABLE public.tm_cached_data ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- Auto-update updated_at trigger
-- =============================================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_users_profile_updated_at
    BEFORE UPDATE ON public.users_profile
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

CREATE TRIGGER trg_subscriptions_updated_at
    BEFORE UPDATE ON public.subscriptions
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- =============================================================================
-- Auth trigger — auto-create profile + free subscription on signup
-- =============================================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
    -- Profile
    INSERT INTO public.users_profile (id, email, full_name, avatar_url)
    VALUES (
        NEW.id,
        NEW.email,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'name'),
        NEW.raw_user_meta_data->>'avatar_url'
    );

    -- Free-tier subscription with Trademark Shield enabled
    INSERT INTO public.subscriptions (user_id, plan_tier, status, active_tools)
    VALUES (
        NEW.id,
        'free',
        'active',
        '{"trademark_shield": true}'::jsonb
    );

    -- Free-tier usage limits
    INSERT INTO public.usage_limits (user_id, tool, limit_type, limit_value, period_end)
    VALUES (
        NEW.id,
        'trademark_shield',
        'searches_per_month',
        5,
        NOW() + INTERVAL '1 month'
    );

    RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- =============================================================================
-- Helper: cleanup expired cache (cron-ready)
-- =============================================================================

CREATE OR REPLACE FUNCTION public.cleanup_expired_cache()
RETURNS INTEGER LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM public.tm_cached_data WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$;
