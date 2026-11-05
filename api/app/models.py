"""Imports every model so Base.metadata knows all tables (used by Alembic)."""

from app.auth.models import AuthFailure, User
from app.core.base import Base
from app.products.models import Product, ProductAlias, UnitConversion
from app.stores.models import Invite, Store, StoreMember

__all__ = [
    "AuthFailure",
    "Base",
    "Product",
    "ProductAlias",
    "UnitConversion",
    "Invite",
    "Store",
    "StoreMember",
    "User",
]
