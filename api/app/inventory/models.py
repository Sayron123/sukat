"""Scans, transactions, and stock movements.

Every table carries store_id. Child rows reference their parent with a composite FK
(parent_id, store_id), so the database itself refuses a row that mixes two stores.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, created_at_col, updated_at_col, uuid_pk

Qty = Numeric(12, 3)

SCAN_TYPES = ("sale", "stock_in")
SCAN_STATUSES = ("pending", "read", "failed", "saved")
TRANSACTION_TYPES = ("sale", "stock_in", "adjustment")
TRANSACTION_STATUSES = ("saved", "voided")


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


class Scan(Base):
    """A photo of a list, and what the AI read from it."""

    __tablename__ = "scans"
    __table_args__ = (
        UniqueConstraint("id", "store_id"),
        UniqueConstraint("store_id", "photo_key"),  # one scan per photo
        CheckConstraint(f"type IN {_in(SCAN_TYPES)}", name="type"),
        CheckConstraint(f"status IN {_in(SCAN_STATUSES)}", name="status"),
        Index("ix_scans_store_id_created_at", "store_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    # Storage key of the photo; always starts with "<store_id>/".
    photo_key: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    ai_result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Why the last read failed, shown to staff with a Retry button.
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Transaction(Base):
    """One saved event that changes stock: a stock-in, a sale, or an adjustment."""

    __tablename__ = "transactions"
    __table_args__ = (
        UniqueConstraint("id", "store_id"),
        # Idempotency: the phone's id for this save. Sending it twice can't save twice.
        UniqueConstraint("store_id", "client_request_id"),
        ForeignKeyConstraint(["scan_id", "store_id"], ["scans.id", "scans.store_id"]),
        CheckConstraint(f"type IN {_in(TRANSACTION_TYPES)}", name="type"),
        CheckConstraint(f"status IN {_in(TRANSACTION_STATUSES)}", name="status"),
        CheckConstraint("total_centavos >= 0", name="total_not_negative"),
        Index("ix_transactions_store_id_created_at", "store_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    scan_id: Mapped[UUID | None] = mapped_column(nullable=True, index=True)
    client_request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # Sum of known line totals. BIGINT: many lines can pass int4's ₱21M limit.
    total_centavos: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="saved")
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()

    items: Mapped[list["TransactionItem"]] = relationship(
        back_populates="transaction",
        order_by="TransactionItem.line_no",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class TransactionItem(Base):
    __tablename__ = "transaction_items"
    __table_args__ = (
        UniqueConstraint("transaction_id", "line_no"),
        ForeignKeyConstraint(
            ["transaction_id", "store_id"],
            ["transactions.id", "transactions.store_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(["product_id", "store_id"], ["products.id", "products.store_id"]),
        CheckConstraint("qty > 0", name="qty_positive"),
        CheckConstraint("qty_base > 0", name="qty_base_positive"),
        CheckConstraint(
            "unit_price_centavos IS NULL OR unit_price_centavos >= 0", name="price_not_negative"
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[UUID] = mapped_column(nullable=False)
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    qty: Mapped[Decimal] = mapped_column(Qty, nullable=False)  # as written: 2 (box)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    qty_base: Mapped[Decimal] = mapped_column(Qty, nullable=False)  # in base unit: 50 (kg)
    # Price per `unit` as written on the list (supplier cost for stock-in). NULL = not written.
    unit_price_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_total_centavos: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    transaction: Mapped[Transaction] = relationship(back_populates="items")


class StockMovement(Base):
    """Every change to a product's stock, with the stock right after it (an audit trail)."""

    __tablename__ = "stock_movements"
    __table_args__ = (
        ForeignKeyConstraint(["product_id", "store_id"], ["products.id", "products.store_id"]),
        ForeignKeyConstraint(
            ["transaction_id", "store_id"], ["transactions.id", "transactions.store_id"]
        ),
        CheckConstraint("qty_change <> 0", name="qty_change_not_zero"),
        Index("ix_stock_movements_product_id_created_at", "product_id", "created_at"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    transaction_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    qty_change: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    stock_after: Mapped[Decimal] = mapped_column(Qty, nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
