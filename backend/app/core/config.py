"""Application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import (
    EmailStr,
    Field,
    SecretStr,
    TypeAdapter,
    ValidationError,
    ValidationInfo,
    field_validator,
    model_validator,
)
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
    login_ip_rate_limit: int = Field(default=5, ge=1, le=10_000)
    login_ip_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)
    login_account_rate_limit: int = Field(default=20, ge=1, le=10_000)
    login_account_rate_window_seconds: int = Field(default=3_600, ge=1, le=86_400)
    refresh_rate_limit: int = Field(default=10, ge=1, le=10_000)
    refresh_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)
    business_rate_limit: int = Field(default=120, ge=1, le=10_000)
    business_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)
    rabbitmq_url: SecretStr | None = None
    rabbitmq_host: str | None = None
    rabbitmq_port: int = Field(default=5672, ge=1, le=65_535)
    rabbitmq_vhost: str = "/retailops"
    rabbitmq_username: str | None = None
    rabbitmq_password: SecretStr | None = None
    outbox_exchange: str = "retailops.email"
    outbox_queue: str = "retailops.email.v1"
    outbox_routing_key: str = "email.deliver.v1"
    outbox_task_name: str = "retailops.email.deliver_v1"
    outbox_batch_size: int = Field(default=25, ge=1, le=25)
    outbox_poll_seconds: float = Field(default=5.0, gt=0, le=60)
    email_retry_delays_seconds: tuple[int, int, int] = (30, 120, 300)
    smtp_host: str | None = None
    smtp_port: int = Field(default=1025, ge=1, le=65_535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from_address: str = "no-reply@retailops.local"
    smtp_starttls: bool = False
    smtp_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    password_reset_ttl_seconds: int = Field(default=900, ge=60, le=3600)
    password_reset_base_url: str = "http://127.0.0.1:5173/reset-password"
    password_reset_email_adapter: Literal["outbox", "memory"] = "outbox"
    forgot_password_ip_rate_limit: int = Field(default=5, ge=1, le=10_000)
    forgot_password_ip_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)
    forgot_password_account_rate_limit: int = Field(default=5, ge=1, le=10_000)
    forgot_password_account_rate_window_seconds: int = Field(
        default=3_600, ge=1, le=86_400
    )
    reset_password_ip_rate_limit: int = Field(default=10, ge=1, le=10_000)
    reset_password_ip_rate_window_seconds: int = Field(default=60, ge=1, le=86_400)

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

    @field_validator(
        "outbox_exchange", "outbox_queue", "outbox_routing_key", "outbox_task_name"
    )
    @classmethod
    def validate_broker_names(cls, value: str, info: ValidationInfo) -> str:
        expected = {
            "outbox_exchange": "retailops.email",
            "outbox_queue": "retailops.email.v1",
            "outbox_routing_key": "email.deliver.v1",
            "outbox_task_name": "retailops.email.deliver_v1",
        }
        field_name = info.field_name
        if value != expected[field_name]:
            raise ValueError(f"{field_name} is frozen by the BE-OUTBOX contract")
        return value

    @field_validator("email_retry_delays_seconds")
    @classmethod
    def validate_email_retry_delays(
        cls, value: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        if value != (30, 120, 300):
            raise ValueError("Email retry delays must be exactly 30,120,300 seconds")
        return value

    @field_validator("password_reset_base_url")
    @classmethod
    def validate_password_reset_base_url(cls, value: str) -> str:
        """Require an explicit HTTP(S) base URL without query or fragment."""
        cleaned = value.strip()
        parsed = urlsplit(cleaned)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("password_reset_base_url must be a clean HTTP(S) URL")
        return cleaned.rstrip("/")

    @model_validator(mode="after")
    def reject_memory_reset_adapter_in_production(self) -> "Settings":
        """Ensure fake in-memory reset email adapter cannot run in production."""
        if (
            self.environment.strip().lower() == "production"
            and self.password_reset_email_adapter == "memory"
        ):
            raise ValueError(
                "In-memory password reset email adapter is forbidden in production"
            )
        return self

    @field_validator("smtp_from_address")
    @classmethod
    def validate_smtp_header_safety(cls, value: str) -> str:
        if not value or "\r" in value or "\n" in value:
            raise ValueError("SMTP sender must be a single non-empty address")
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

    def require_rabbitmq_url(self) -> str:
        if self.rabbitmq_url is not None:
            return self.rabbitmq_url.get_secret_value()
        if (
            self.rabbitmq_host is None
            or self.rabbitmq_username is None
            or self.rabbitmq_password is None
        ):
            raise RuntimeError("RabbitMQ is not configured")
        username = quote(self.rabbitmq_username, safe="")
        password = quote(self.rabbitmq_password.get_secret_value(), safe="")
        vhost = quote(self.rabbitmq_vhost, safe="")
        return (
            f"amqp://{username}:{password}@{self.rabbitmq_host}:"
            f"{self.rabbitmq_port}/{vhost}"
        )

    def require_smtp_host(self) -> str:
        if self.smtp_host is None:
            raise RuntimeError("SMTP is not configured")
        return self.smtp_host

    def validate_email_worker_configuration(self) -> None:
        """Fail worker startup without a complete environment-specific SMTP setup."""
        if self.smtp_host is None:
            raise RuntimeError("Email worker requires an SMTP host")
        if (self.smtp_username is None) != (self.smtp_password is None):
            raise RuntimeError("SMTP username and password must be configured together")
        if self.environment.casefold() == "production":
            if self.smtp_host.casefold() in {"mailpit", "localhost", "127.0.0.1"}:
                raise RuntimeError("Production email worker cannot use local SMTP")
            if not self.smtp_starttls:
                raise RuntimeError("Production email worker requires STARTTLS")
            try:
                TypeAdapter(EmailStr).validate_python(self.smtp_from_address)
            except ValidationError as error:
                raise RuntimeError(
                    "Production email worker requires a valid provider sender"
                ) from error

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
