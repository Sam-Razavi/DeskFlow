from functools import lru_cache
from typing import Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# HS256 keys shorter than the hash size are weak, and PyJWT warns about them.
MIN_PRODUCTION_SECRET_LENGTH = 32
DEV_JWT_SECRET = "dev-only-secret-change-me-before-deploying"


class Settings(BaseSettings):
    # A rejected value is often a secret that was almost right, so never echo it into the logs.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_name: str = "DeskFlow API"
    environment: str = "development"

    database_url: str = "postgresql+asyncpg://deskflow:deskflow@localhost:5432/deskflow"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = DEV_JWT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Sign-in throttling. A person gets this many wrong passwords per window before being asked to
    # wait; a single address gets more, since an office can share one.
    login_max_failures: int = 5
    login_max_failures_per_ip: int = 30
    login_window_seconds: int = 900

    cors_origins: list[str] = ["http://localhost:4200"]

    @field_validator("database_url")
    @classmethod
    def use_asyncpg_driver(cls, v: str) -> str:
        # Railway and most hosts expose a plain postgres:// URL; SQLAlchemy needs the async driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v.removeprefix(prefix)
        return v

    @model_validator(mode="after")
    def require_real_secret_in_production(self) -> Self:
        if self.environment == "production":
            if self.jwt_secret == DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be set in production")
            if len(self.jwt_secret) < MIN_PRODUCTION_SECRET_LENGTH:
                raise ValueError(
                    f"JWT_SECRET must be at least {MIN_PRODUCTION_SECRET_LENGTH} characters "
                    "(generate one with: openssl rand -hex 32)"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
