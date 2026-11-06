"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
DEVELOPMENT_CORS_ORIGIN = "http://127.0.0.1:5173"


class Settings(BaseSettings):
    """Environment-backed application settings."""

    app_name: str = "RetailOps API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    db_host: str
    db_port: int = 3306
    db_name: str
    db_user: str
    db_password: SecretStr
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 10
    db_pool_recycle_seconds: int = 1800
    cors_origins: str = ""

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        """Validate a comma-separated exact-origin allowlist."""
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or "*" in origin
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("CORS origins must be exact HTTP(S) origins")
        return ",".join(origins)

    @property
    def cors_origin_allowlist(self) -> list[str]:
        """Return the validated exact origins for FastAPI middleware."""
        if self.cors_origins:
            return self.cors_origins.split(",")
        if self.environment.casefold() == "development":
            return [DEVELOPMENT_CORS_ORIGIN]
        return []

    @property
    def database_url(self) -> URL:
        """Build a SQLAlchemy URL without string interpolation of credentials."""
        return URL.create(
            drivername="mysql+pymysql",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"charset": "utf8mb4"},
        )

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="RETAILOPS_",
        extra="ignore",
        frozen=True,
    )


@lru_cache
def get_settings() -> Settings:
    """Return the immutable process-wide settings instance."""
    return Settings()
