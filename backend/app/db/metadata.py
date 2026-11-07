"""Central registry of reviewed ORM metadata for Alembic."""

from app.db.base import Base
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.categories.models import Category
from app.modules.suppliers.models import Supplier

REGISTERED_MODELS = (
    User,
    StaffApprovalRequest,
    AuthSession,
    RefreshToken,
    Category,
    Supplier,
)
metadata = Base.metadata
