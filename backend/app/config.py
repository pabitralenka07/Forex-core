"""Application Configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    app_name: str = "Currency Converter API"
    app_version: str = "0.1.0"
    app_env: Literal["development", "testing", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/v1"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:8501", "http://127.0.0.1:8501"]

    # Provider settings
    primary_provider: str = "frankfurter"
    frankfurter_base_url: str = "https://api.frankfurter.dev/v1"
    secondary_provider: str = "exchangerate_api"
    exchangerate_api_base_url: str = "https://open.er-api.com/v6"
    exchangerate_api_key: str | None = None
    provider_timeout_seconds: float = 5.0

    # Financial conversion settings
    rounding_policy: Literal["ROUND_HALF_UP", "ROUND_HALF_EVEN"] = "ROUND_HALF_UP"
    pivot_currency: str = "EUR"
    large_movement_threshold_pct: float = 15.0

    # Caching and Resilience settings
    cache_backend: Literal["memory", "redis"] = "memory"
    cache_ttl_seconds: int = 3600
    cache_max_size: int = 1000
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_recovery_timeout_seconds: float = 30.0
    retry_max_attempts: int = 3
    retry_min_wait_seconds: float = 0.2
    retry_max_wait_seconds: float = 1.0

    # Database settings
    database_url: str = "sqlite+aiosqlite:///./currency_converter.db"
    sync_database_url: str = "sqlite:///./currency_converter.db"
    db_echo: bool = False
    background_refresh_enabled: bool = True
    background_refresh_interval_seconds: int = 3600

    # Security and Rate Limiting settings
    rate_limit_free: str = "60/minute"
    rate_limit_pro: str = "300/minute"
    rate_limit_enterprise: str = "1200/minute"
    security_headers_enabled: bool = True
    hsts_max_age_seconds: int = 31536000
    # When False, falls back to IP rate limiting; when True, strictly enforces X-API-Key
    require_api_key: bool = False

    # Model settings configuration
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
