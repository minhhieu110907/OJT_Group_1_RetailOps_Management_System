"""Central registry of reviewed ORM metadata for Alembic."""

from app.db.base import Base
from app.modules.auth.models import (
    AuthSession,
    RefreshToken,
    StaffApprovalRequest,
    User,
)

REGISTERED_MODELS = (User, StaffApprovalRequest, AuthSession, RefreshToken)
metadata = Base.metadata
