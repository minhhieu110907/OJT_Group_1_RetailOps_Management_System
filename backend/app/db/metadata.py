"""Central SQLAlchemy metadata registry for Alembic."""

from app.db.base import Base
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.categories.models import Category
from app.modules.notifications.models import AdminNotification
from app.modules.suppliers.models import Supplier

REGISTERED_MODELS = (
    User,
    StaffApprovalRequest,
    AuthSession,
    RefreshToken,
    AdminNotification,
    Category,
    Supplier,
)
metadata = Base.metadata

__all__ = ["Base", "REGISTERED_MODELS", "metadata"]
