"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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
    jwt_secret: SecretStr | None = None
    csrf_secret: SecretStr | None = None
    idempotency_secret: SecretStr | None = None
    jwt_issuer: str = "retailops-api"
    jwt_audience: str = "retailops-api"
    access_token_ttl_seconds: int = 900
    session_ttl_seconds: int = 28_800
    csrf_ttl_seconds: int = 1_800
    refresh_cookie_name: str = "retailops_refresh"
    csrf_cookie_name: str = "retailops_csrf"
    auth_cookie_path: str = "/api/v1/auth"
    cookie_secure: bool | None = None
    redis_url: SecretStr = SecretStr("redis://redis:6379/0")
    redis_pool_size: int = Field(default=10, ge=1, le=100)
    redis_connect_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    redis_socket_timeout_seconds: float = Field(default=1.0, gt=0, le=10)
    rate_limit_namespace: str = "retailops:rate-limit"
    register_rate_limit: int = Field(default=5, ge=1, le=10_000)
    register_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)

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

    @field_validator("redis_url")
    @classmethod
    def validate_redis_url(cls, value: SecretStr) -> SecretStr:
        """Require an explicit Redis URI supported by redis-py."""
        parsed = urlsplit(value.get_secret_value())
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("Redis URL must use redis:// or rediss:// with a host")
        return value

    @field_validator("rate_limit_namespace")
    @classmethod
    def validate_rate_limit_namespace(cls, value: str) -> str:
        """Keep Redis keys in a non-empty, whitespace-free namespace."""
        if not value or any(character.isspace() for character in value):
            raise ValueError(
                "Rate-limit namespace must be non-empty without whitespace"
            )
        return value

    @model_validator(mode="after")
    def validate_auth_configuration(self) -> "Settings":
        """Reject unsafe TTLs and incomplete production secret configuration."""
        if not 1 <= self.access_token_ttl_seconds <= 900:
            raise ValueError("Access token TTL must be between 1 and 900 seconds")
        if not 1 <= self.session_ttl_seconds <= 28_800:
            raise ValueError("Session TTL must be between 1 and 28800 seconds")
        if not 60 <= self.csrf_ttl_seconds <= 3_600:
            raise ValueError("CSRF TTL must be between 60 and 3600 seconds")
        for name, secret in (("JWT", self.jwt_secret), ("CSRF", self.csrf_secret)):
            if secret is not None:
                secret_value = secret.get_secret_value()
                if len(secret_value.encode()) < 32 or secret_value.startswith(
                    "CHANGE_ME"
                ):
                    raise ValueError(
                        f"{name} secret must be a non-placeholder of at least 32 bytes"
                    )
        if self.idempotency_secret is not None:
            secret_value = self.idempotency_secret.get_secret_value()
            if len(secret_value.encode()) < 32 or secret_value.startswith("CHANGE_ME"):
                raise ValueError(
                    "Idempotency secret must be a non-placeholder of at least 32 bytes"
                )
        if self.environment.casefold() == "production":
            if self.jwt_secret is None or self.csrf_secret is None:
                raise ValueError("Production requires JWT and CSRF secrets")
            if self.cookie_secure is False:
                raise ValueError("Production auth cookies must be Secure")
        return self

    @property
    def cors_origin_allowlist(self) -> list[str]:
        """Return the validated exact origins for FastAPI middleware."""
        if self.cors_origins:
            return self.cors_origins.split(",")
        if self.environment.casefold() == "development":
            return [DEVELOPMENT_CORS_ORIGIN]
        return []

    @property
    def auth_cookie_secure(self) -> bool:
        """Use Secure cookies in production while allowing explicit local HTTP."""
        if self.environment.casefold() == "production":
            return True
        return bool(self.cookie_secure)

    def require_auth_secrets(self) -> tuple[bytes, bytes]:
        """Return configured secrets or fail closed before auth work begins."""
        if self.jwt_secret is None or self.csrf_secret is None:
            raise RuntimeError("Authentication secrets are not configured")
        return (
            self.jwt_secret.get_secret_value().encode(),
            self.csrf_secret.get_secret_value().encode(),
        )

    def require_idempotency_secret(self) -> bytes:
        """Return the HMAC key or fail closed before processing a command."""
        if self.idempotency_secret is None:
            raise RuntimeError("Idempotency secret is not configured")
        return self.idempotency_secret.get_secret_value().encode()

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
