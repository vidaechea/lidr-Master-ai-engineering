from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "DEBUG"

    # ── Database ──────────────────────────────────────────────────────────────
    database_url: str = "postgresql+asyncpg://estimator:estimator_dev@localhost:5432/estimator"

    # ── Redis / Queue ─────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379"

    # ── JWT ───────────────────────────────────────────────────────────────────
    secret_key: str = "dev_secret_change_me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ── AI Engine ─────────────────────────────────────────────────────────────
    ai_engine_url: str = "http://localhost:8001"
    # Shared secret with the ai-engine service.
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    internal_api_key: Optional[str] = None

    # ── CORS ──────────────────────────────────────────────────────────────────
    cors_origins: list[str] = ["http://localhost:4200", "http://localhost:3000"]


settings = Settings()
