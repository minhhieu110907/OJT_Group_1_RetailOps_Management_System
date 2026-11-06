"""MySQL integration tests for the explicit Admin seed."""

from datetime import datetime

import pytest
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.auth.security import PasswordHasher
from app.modules.auth.seed import AdminSeedConflictError, seed_admin

pytestmark = pytest.mark.integration

SEED_EMAIL = "t3c9a19_seed_admin@example.com"


@pytest.fixture(autouse=True)
def clean_seed_identity(migrated_integration_engine: Engine) -> None:
    yield
    with Session(migrated_integration_engine) as session, session.begin():
        session.execute(
            delete(User).where(User.email_normalized.like("t3c9a19_seed_%"))
        )


def test_admin_seed_is_idempotent_without_password_rotation(
    migrated_integration_engine: Engine,
) -> None:
    hasher = PasswordHasher(work_factor=4)
    with Session(migrated_integration_engine) as session:
        assert seed_admin(
            session,
            email=f"  {SEED_EMAIL.upper()}  ",
            password=SecretStr("first password"),
            password_hasher=hasher,
        )
        original_hash = session.scalar(
            select(User.password_hash).where(User.email_normalized == SEED_EMAIL)
        )

        assert not seed_admin(
            session,
            email=SEED_EMAIL,
            password=SecretStr("different password"),
            password_hasher=hasher,
        )
        admin = session.scalar(select(User).where(User.admin_slot == 1))
        admin_count = session.scalar(
            select(func.count()).select_from(User).where(User.admin_slot == 1)
        )

    assert admin is not None
    assert admin.role == "ADMIN"
    assert admin.status == "ACTIVE"
    assert admin.password_hash == original_hash
    assert admin_count == 1


def test_admin_seed_fails_closed_for_different_existing_admin(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        session.add(
            User(
                email_normalized="t3c9a19_seed_existing@example.com",
                password_hash="test-only-hash",
                role="ADMIN",
                status="ACTIVE",
                admin_slot=1,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        with pytest.raises(AdminSeedConflictError):
            seed_admin(
                session,
                email="t3c9a19_seed_other@example.com",
                password=SecretStr("password"),
                password_hasher=PasswordHasher(work_factor=4),
            )


def test_admin_seed_fails_closed_when_email_is_occupied(
    migrated_integration_engine: Engine,
) -> None:
    now = datetime(2026, 11, 6, 8, 0)
    with Session(migrated_integration_engine) as session:
        session.add(
            User(
                email_normalized=SEED_EMAIL,
                password_hash="test-only-hash",
                role="STAFF",
                status="ACTIVE",
                admin_slot=None,
                last_reapplied_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

        with pytest.raises(AdminSeedConflictError):
            seed_admin(
                session,
                email=SEED_EMAIL,
                password=SecretStr("password"),
                password_hasher=PasswordHasher(work_factor=4),
            )
