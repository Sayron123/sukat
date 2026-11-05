from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, created_at_col, updated_at_col, uuid_pk
from app.products.constants import CATEGORIES, sql_in_list

# Quantities: up to 999,999,999.999 with 3 decimals (e.g. 2.5 kg, 0.125 m).
Qty = Numeric(12, 3)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (
        # Lets aliases/conversions reference (id, store_id) together, so the database itself
        # guarantees an alias belongs to a product of the SAME store.
        UniqueConstraint("id", "store_id"),
        # No two products in one store with the same name (ignoring upper/lower case).
        Index("uq_products_store_id_lower_name", "store_id", func.lower(text("name")), unique=True),
        Index("ix_products_store_id_archived", "store_id", "archived"),
        CheckConstraint(f"category IN {sql_in_list(CATEGORIES)}", name="category"),
        CheckConstraint("base_unit = lower(base_unit)", name="base_unit_lowercase"),
        CheckConstraint("price_centavos IS NULL OR price_centavos >= 0", name="price_not_negative"),
        CheckConstraint(
            "low_stock_level IS NULL OR low_stock_level >= 0", name="low_stock_not_negative"
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    base_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    # Price per base_unit in centavos (₱125.50 = 12550). NULL = not priced yet.
    price_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Changed only by stock movements (later phase), never by the product form.
    stock_qty: Mapped[Decimal] = mapped_column(Qty, nullable=False, server_default="0")
    low_stock_level: Mapped[Decimal | None] = mapped_column(Qty, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    aliases: Mapped[list["ProductAlias"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductAlias.alias",
        lazy="selectin",
        overlaps="conversions",
    )
    conversions: Mapped[list["UnitConversion"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="UnitConversion.from_unit",
        lazy="selectin",
        overlaps="aliases",
    )


class ProductAlias(Base):
    """Another name staff use for a product, e.g. "sem" for cement. Stored lowercase."""

    __tablename__ = "product_aliases"
    __table_args__ = (
        UniqueConstraint("store_id", "alias"),  # one alias points to one product per store
        ForeignKeyConstraint(
            ["product_id", "store_id"], ["products.id", "products.store_id"], ondelete="CASCADE"
        ),
        CheckConstraint("alias = lower(alias)", name="alias_lowercase"),
        CheckConstraint("length(alias) > 0", name="alias_not_empty"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(80), nullable=False)

    product: Mapped[Product] = relationship(back_populates="aliases", overlaps="conversions")


class UnitConversion(Base):
    """1 from_unit = factor base_unit. Example for nails (base kg): 1 box = 25 kg."""

    __tablename__ = "unit_conversions"
    __table_args__ = (
        UniqueConstraint("product_id", "from_unit"),
        ForeignKeyConstraint(
            ["product_id", "store_id"], ["products.id", "products.store_id"], ondelete="CASCADE"
        ),
        CheckConstraint("factor > 0", name="factor_positive"),
        CheckConstraint("from_unit = lower(from_unit)", name="from_unit_lowercase"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(nullable=False)
    from_unit: Mapped[str] = mapped_column(String(20), nullable=False)
    factor: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)

    product: Mapped[Product] = relationship(back_populates="conversions", overlaps="aliases")
