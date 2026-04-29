"""
Application settings.

Uses pydantic-settings to load from environment variables with validation.
All settings are immutable (frozen) and cached via lru_cache.

Usage:
    from scalemyprints.core.config import get_settings
    settings = get_settings()
    api_key = settings.openai_api_key
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Precedence: OS env > .env.local > .env > defaults
    """

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    # ---------------- Environment ----------------
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # ---------------- Server ----------------
    worker_host: str = "0.0.0.0"  # noqa: S104 — intentional, bind all interfaces
    worker_port: int = 8000
    worker_log_level: LogLevel = LogLevel.INFO
    worker_cors_origins: str = "http://localhost:3000"

    # ---------------- Supabase ----------------
    next_public_supabase_url: str = Field(default="", alias="NEXT_PUBLIC_SUPABASE_URL")
    next_public_supabase_anon_key: SecretStr = Field(
        default=SecretStr(""), alias="NEXT_PUBLIC_SUPABASE_ANON_KEY"
    )
    supabase_service_role_key: SecretStr = Field(default=SecretStr(""))
    supabase_jwt_secret: SecretStr = Field(default=SecretStr(""))
    # Server-side alias — accept SUPABASE_URL too, falls back to NEXT_PUBLIC_SUPABASE_URL
    supabase_url_override: str = Field(default="", alias="SUPABASE_URL")

    @property
    def supabase_url(self) -> str:
        """Resolved Supabase URL — prefers SUPABASE_URL over NEXT_PUBLIC_*."""
        return self.supabase_url_override or self.next_public_supabase_url

    # ---------------- Provider abstraction ----------------
    llm_provider: Literal["auto_route", "openai", "claude", "gemini", "groq"] = "openai"
    scraping_provider: Literal["disabled", "playwright", "apify", "brightdata"] = "disabled"
    email_provider: Literal["resend", "supabase"] = "resend"
    cache_provider: Literal["memory", "redis"] = "memory"
    image_gen_provider: Literal["disabled", "falai_free", "falai_paid", "replicate"] = "disabled"
    feature_paid_infrastructure_enabled: bool = False

    # ---------------- LLM keys ----------------
    openai_api_key: SecretStr = Field(default=SecretStr(""))
    openai_model_cheap: str = "gpt-4o-mini"
    openai_model_smart: str = "gpt-4o"

    anthropic_api_key: SecretStr = Field(default=SecretStr(""))
    anthropic_model_cheap: str = "claude-haiku-4-5-20251001"
    anthropic_model_smart: str = "claude-sonnet-4-6"

    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    gemini_model: str = "gemini-1.5-flash"

    groq_api_key: SecretStr = Field(default=SecretStr(""))
    groq_model: str = "llama-3.3-70b-versatile"

    # ---------------- Trademark APIs ----------------
    # US provider — "marker" (default, no key needed) or "uspto" (requires USPTO API key)
    us_trademark_provider: str = "marker"
    uspto_api_base_url: str = "https://tsdrapi.uspto.gov"
    uspto_api_key: SecretStr = Field(default=SecretStr(""))
    uspto_rate_limit_per_min: int = 60

    # Marker API (3rd-party USPTO data aggregator)
    marker_api_base_url: str = "https://markerapi.com"
    marker_api_username: SecretStr = Field(default=SecretStr(""))
    marker_api_password: SecretStr = Field(default=SecretStr(""))

    # EU — TMview is the default (WIPO/EUIPO joint platform, public)
    eu_trademark_provider: str = "tmview"
    tmview_api_base_url: str = "https://www.tmdn.org"
    euipo_api_base_url: str = "https://euipo.europa.eu/copla"

    # UK
    ukipo_api_base_url: str = "https://trademarks.ipo.gov.uk"

    # AU
    ipau_api_base_url: str = "https://search.ipaustralia.gov.au"

    # ---------------- Niche Radar ----------------
    # Trends provider — "google" (free, default) or "fallback" (no data)
    niche_trends_provider: str = "google"
    # Marketplace provider — "etsy_public" (free) or "apify" (paid, optional)
    niche_marketplace_provider: str = "etsy_public"
    # Events provider — "static" (curated JSON) or "calendarific" (paid API)
    niche_events_provider: str = "static"
    # LLM expander — "openai" or "disabled"
    niche_llm_provider: str = "openai"

    # Optional paid integrations
    apify_api_token: SecretStr = Field(default=SecretStr(""))
    apify_etsy_actor_id: str = "epctex/etsy-scraper"
    calendarific_api_key: SecretStr = Field(default=SecretStr(""))

    # ---------------- Email ----------------
    resend_api_key: SecretStr = Field(default=SecretStr(""))
    resend_from_email: str = "hello@scalemyprints.com"
    resend_from_name: str = "ScaleMyPrints"

    # ---------------- Observability ----------------
    sentry_dsn: str = ""
    sentry_environment: str = "development"

    # ---------------- Security ----------------
    master_encryption_key: SecretStr = Field(default=SecretStr(""))
    internal_api_secret: SecretStr = Field(default=SecretStr(""))

    # ---------------- Cache ----------------
    redis_url: str = "redis://localhost:6379/0"

    # ---------------- Rate limiting ----------------
    rate_limit_per_minute: int = 60
    rate_limit_trademark_free_tier: int = 5

    # ---------------- Validators ----------------

    @field_validator("worker_cors_origins")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        # Comma-separated string; we parse it later
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse comma-separated CORS origins into a list."""
        return [origin.strip() for origin in self.worker_cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == Environment.PRODUCTION

    @property
    def is_development(self) -> bool:
        return self.environment == Environment.DEVELOPMENT

    @property
    def is_test(self) -> bool:
        return self.environment == Environment.TEST


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached settings instance.

    The first call reads from env/files; subsequent calls return cached.
    For tests, call get_settings.cache_clear() between runs.
    """
    return Settings()
