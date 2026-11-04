"""Imports every model so Base.metadata knows all tables (used by Alembic)."""

from app.auth.models import User
from app.core.base import Base
from app.stores.models import Invite, Store, StoreMember

__all__ = ["Base", "Invite", "Store", "StoreMember", "User"]
