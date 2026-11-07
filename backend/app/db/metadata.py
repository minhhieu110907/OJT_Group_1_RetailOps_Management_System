"""Central registry of reviewed ORM metadata for Alembic."""

from app.db.base import Base
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)
from app.modules.products.models import (
    Category,
    Inventory,
    Product,
)

REGISTERED_MODELS = (
    User,
    StaffApprovalRequest,
    AuthSession,
    RefreshToken,
    Category,
    Product,
    Inventory,
)
metadata = Base.metadata
