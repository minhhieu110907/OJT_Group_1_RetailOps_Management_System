"""Explicit, environment-driven Admin seed command."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import PROJECT_ROOT
from app.modules.auth.models import User, UserRole, UserStatus
from app.modules.auth.security import PasswordHasher, normalize_email


class AdminSeedConflictError(RuntimeError):
    """Raised when seed identity conflicts with existing data."""


class AdminSeedSettings(BaseSettings):
    """Credentials loaded only when the explicit seed command runs."""

    email: str
    password: SecretStr

    model_config = SettingsConfigDict(
        env_file=Path(PROJECT_ROOT) / ".env",
        env_file_encoding="utf-8",
        env_prefix="RETAILOPS_ADMIN_SEED_",
        extra="ignore",
        frozen=True,
    )


def seed_admin(
    session: Session,
    *,
    email: str,
    password: SecretStr,
    password_hasher: PasswordHasher | None = None,
) -> bool:
    """Create the sole Admin or no-op for the same existing identity."""
    normalized_email = normalize_email(email)
    existing_admin = session.scalar(select(User).where(User.admin_slot == 1))
    if existing_admin is not None:
        if existing_admin.email_normalized != normalized_email:
            raise AdminSeedConflictError("A different Admin identity already exists")
        return False

    existing_identity = session.scalar(
        select(User).where(User.email_normalized == normalized_email)
    )
    if existing_identity is not None:
        raise AdminSeedConflictError("Admin seed identity is already occupied")

    now = datetime.now(UTC).replace(tzinfo=None)
    hasher = password_hasher or PasswordHasher()
    admin = User(
        email_normalized=normalized_email,
        password_hash=hasher.hash(password.get_secret_value()),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
        admin_slot=1,
        last_reapplied_at=None,
        created_at=now,
        updated_at=now,
    )
    session.add(admin)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise AdminSeedConflictError(
            "Admin seed conflicted with existing data"
        ) from error
    return True


def main() -> None:
    """Run the explicit Admin seed without printing credentials."""
    from app.db.session import SessionLocal

    settings = AdminSeedSettings()
    with SessionLocal() as session:
        created = seed_admin(
            session,
            email=settings.email,
            password=settings.password,
        )
    outcome = "created" if created else "already exists"
    print(f"Admin seed completed: {outcome}")


if __name__ == "__main__":
    main()
