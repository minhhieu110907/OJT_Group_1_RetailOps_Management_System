"""Declarative metadata shared by SQLAlchemy models and Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for future reviewed ORM models."""
