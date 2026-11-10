import csv
import io
from collections.abc import Iterable, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, case, select
from sqlalchemy.orm import Session, aliased

from app.auth.models import User
from app.insights.reports import STORE_TZ
from app.inventory.models import StockMovement, Transaction, TransactionItem
from app.products.models import Product, ProductAlias

BOM = "﻿"
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")
_BATCH = 1000


def safe_text(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return safe_text(value)
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, datetime):
        return value.astimezone(STORE_TZ).isoformat(timespec="seconds")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f") if value == value.to_integral() else str(value)
    return str(value)


def pesos(centavos: int | None) -> str | None:
    if centavos is None:
        return None
    sign = "-" if centavos < 0 else ""
    whole, cents = divmod(abs(centavos), 100)
    return f"{sign}{whole}.{cents:02d}"


class _Num(str):
    pass


def _row(values: Sequence[Any]) -> list[str]:
    return [str(v) if isinstance(v, _Num) else _cell(v) for v in values]


def to_csv(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    out = io.StringIO()
    out.write(BOM)
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow(_row(row))
    return out.getvalue()


def _money(centavos: int | None) -> _Num | None:
    p = pesos(centavos)
    return _Num(p) if p is not None else None


PRODUCT_HEADER = [
    "product_id",
    "name",
    "other_names",
    "category",
    "base_unit",
    "price_peso",
    "stock_qty",
    "low_stock_level",
    "archived",
    "created_at",
    "updated_at",
]


def products_csv(db: Session, store_id: UUID) -> str:
    aliases: dict[UUID, list[str]] = {}
    for product_id, alias in db.execute(
        select(ProductAlias.product_id, ProductAlias.alias)
        .where(ProductAlias.store_id == store_id)
        .order_by(ProductAlias.alias)
    ):
        aliases.setdefault(product_id, []).append(alias)

    products = db.scalars(
        select(Product)
        .where(Product.store_id == store_id)
        .order_by(Product.name, Product.id)
        .execution_options(yield_per=_BATCH)
    )
    return to_csv(
        PRODUCT_HEADER,
        (
            [
                p.id,
                p.name,
                "; ".join(aliases.get(p.id, [])),
                p.category,
                p.base_unit,
                _money(p.price_centavos),
                p.stock_qty,
                p.low_stock_level,
                p.archived,
                p.created_at,
                p.updated_at,
            ]
            for p in products
        ),
    )


TRANSACTION_HEADER = [
    "transaction_id",
    "created_at",
    "type",
    "status",
    "created_by",
    "voided_at",
    "voided_by",
    "transaction_total_peso",
    "line_no",
    "product_id",
    "product_name",
    "qty",
    "unit",
    "qty_base",
    "base_unit",
    "unit_price_peso",
    "line_total_peso",
]


def transactions_csv(db: Session, store_id: UUID) -> str:
    creator = aliased(User)
    voider = aliased(User)
    rows = db.execute(
        select(
            Transaction,
            TransactionItem,
            Product.name,
            Product.base_unit,
            creator.full_name,
            voider.full_name,
        )
        .outerjoin(
            TransactionItem,
            and_(
                TransactionItem.transaction_id == Transaction.id,
                TransactionItem.store_id == Transaction.store_id,
            ),
        )
        .outerjoin(
            Product,
            and_(Product.id == TransactionItem.product_id, Product.store_id == store_id),
        )
        .outerjoin(creator, creator.id == Transaction.created_by)
        .outerjoin(voider, voider.id == Transaction.voided_by)
        .where(Transaction.store_id == store_id)
        .order_by(Transaction.created_at, Transaction.id, TransactionItem.line_no)
        .execution_options(yield_per=_BATCH)
    )

    def lines():
        for t, item, product_name, base_unit, created_by, voided_by in rows:
            yield [
                t.id,
                t.created_at,
                t.type,
                t.status,
                created_by,
                t.voided_at,
                voided_by,
                _money(t.total_centavos),
                item.line_no if item else None,
                item.product_id if item else None,
                product_name,
                item.qty if item else None,
                item.unit if item else None,
                item.qty_base if item else None,
                base_unit,
                _money(item.unit_price_centavos) if item else None,
                _money(item.line_total_centavos) if item else None,
            ]

    return to_csv(TRANSACTION_HEADER, lines())


MOVEMENT_HEADER = [
    "movement_id",
    "created_at",
    "kind",
    "product_id",
    "product_name",
    "qty_change",
    "stock_after",
    "base_unit",
    "transaction_id",
    "created_by",
]

_KIND = case((StockMovement.is_reversal, "void"), else_=Transaction.type)


def stock_movements_csv(db: Session, store_id: UUID) -> str:
    rows = db.execute(
        select(StockMovement, _KIND, Product.name, Product.base_unit, User.full_name)
        .join(
            Transaction,
            and_(
                Transaction.id == StockMovement.transaction_id,
                Transaction.store_id == StockMovement.store_id,
            ),
        )
        .join(
            Product,
            and_(
                Product.id == StockMovement.product_id, Product.store_id == StockMovement.store_id
            ),
        )
        .outerjoin(User, User.id == StockMovement.created_by)
        .where(StockMovement.store_id == store_id)
        .order_by(StockMovement.created_at, StockMovement.id)
        .execution_options(yield_per=_BATCH)
    )
    return to_csv(
        MOVEMENT_HEADER,
        (
            [
                m.id,
                m.created_at,
                kind,
                m.product_id,
                name,
                m.qty_change,
                m.stock_after,
                unit,
                m.transaction_id,
                who,
            ]
            for m, kind, name, unit, who in rows
        ),
    )
