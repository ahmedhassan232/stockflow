"""Environment-driven application settings (12-factor)."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "StockFlow"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    api_v1_prefix: str = "/api/v1"

    # Comma-separated explicit allowlist of browser origins.
    cors_origins: str = ""

    # Runtime role (must be NOSUPERUSER / NOBYPASSRLS) and migration role (schema owner).
    database_url: str = Field(min_length=1)
    migration_database_url: str | None = None
    db_app_user: str = "stockflow_app"
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 10

    redis_url: str = Field(min_length=1)
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    health_check_timeout_seconds: float = 3.0

    # ── Authentication ──
    jwt_secret_key: str = Field(min_length=32)
    jwt_issuer: str = "stockflow"
    access_token_ttl_seconds: int = 900  # 15 minutes
    refresh_token_ttl_days: int = 14
    password_reset_ttl_minutes: int = 30
    refresh_cookie_name: str = "sf_refresh"
    # None → secure in production, plain in development.
    cookie_secure: bool | None = None
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    argon2_time_cost: int = 3
    argon2_memory_kib: int = 65536
    login_max_failures: int = 5
    login_lockout_seconds: int = 900
    auth_rate_limit_per_minute: int = 30

    # ── Email ──
    frontend_url: str = "http://localhost:8080"
    smtp_host: str = "mailpit"
    smtp_port: int = 1025
    smtp_from: str = "no-reply@stockflow.local"
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cookie_secure_effective(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def docs_enabled(self) -> bool:
        return not self.is_production

    @model_validator(mode="after")
    def _validate_production(self) -> "Settings":
        if self.is_production and "*" in self.cors_origin_list:
            raise ValueError("CORS_ORIGINS must be an explicit allowlist in production")
        if self.is_production and self.jwt_secret_key.startswith("change-me"):
            raise ValueError("JWT_SECRET_KEY must be replaced in production")
        if self.is_production and not self.cookie_secure_effective:
            raise ValueError("Refresh cookie must be Secure in production")
        if self.cookie_samesite == "none" and not self.cookie_secure_effective:
            raise ValueError("SameSite=None cookies require COOKIE_SECURE=true")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
