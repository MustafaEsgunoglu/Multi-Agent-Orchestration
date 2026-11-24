from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "staging", "production", "test"] = "development"
    app_name: str = "Multi-Agent Orchestration Platform"
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Database & Redis
    database_url: str = (
        "postgresql+asyncpg://app_user:app_password@localhost:5432/orchestrator"
    )
    redis_url: str = "redis://localhost:6379/0"

    # JWT Auth
    jwt_secret_key: str = "dev-insecure-jwt-secret-change-in-production-32bytes"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # AES-256-GCM Master Key (32-byte key as URL-safe base64 or 64-char hex)
    master_encryption_key: str = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="

    # Execution Safety Guardrails
    default_recursion_limit: int = 25
    max_recursion_limit: int = 50

    # Observability (Optional: Langfuse Cloud)
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Optional provider fallback key for local development (never logged)
    deepseek_api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
