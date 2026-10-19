from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://invoicing:invoicing@localhost:5432/invoicing"
    redis_url: str = "redis://localhost:6379/0"
    # Required in every environment; there is deliberately no default.
    jwt_secret: str
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    rate_limit_per_minute: int = 120
    webhook_max_attempts: int = 6
    # Hosts the worker may post to even though they resolve to private addresses (the demo's receiver)
    webhook_allowed_hosts: list[str] = []
    otel_endpoint: str | None = None  # e.g. http://jaeger:4318 ; tracing is off when unset
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8081"]


@lru_cache
def settings() -> Settings:
    return Settings()
