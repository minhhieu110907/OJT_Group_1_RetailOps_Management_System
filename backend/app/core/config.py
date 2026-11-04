"""Application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Environment-backed application settings."""

    app_name: str = "RetailOps API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        env_prefix="RETAILOPS_",
        extra="ignore",
        frozen=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return the immutable process-wide settings instance."""
    return Settings()
