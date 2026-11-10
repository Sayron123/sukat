"""Imports every model so Base.metadata knows all tables (used by Alembic)."""

from app.ai.models import AIUsage
from app.auth.models import AuthFailure, AuthToken, User
from app.core.base import Base
from app.core.outbox import OutboxEmail
from app.inventory.models import Scan, StockMovement, Transaction, TransactionItem
from app.products.models import Product, ProductAlias, UnitConversion
from app.stores.models import Invite, Store, StoreMember

__all__ = [
    "AIUsage",
    "Scan",
    "StockMovement",
    "Transaction",
    "TransactionItem",
    "AuthFailure",
    "AuthToken",
    "Base",
    "Product",
    "ProductAlias",
    "UnitConversion",
    "Invite",
    "OutboxEmail",
    "Store",
    "StoreMember",
    "User",
]
