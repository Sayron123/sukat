"""Saving a stock-in: one database transaction that records what arrived and updates stock.

Guarantees:
- Idempotent: the same client_request_id saves once; repeats get the first result.
- No lost updates: product rows are locked (SELECT ... FOR UPDATE) before stock changes,
  so two saves at the same moment both count.
- All or nothing: any error rolls back every row of the save.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.schemas import ScanLine
from app.auth.deps import CurrentMember
from app.core.errors import Conflict, Forbidden, Invalid, NotFound
from app.inventory.models import Scan, StockMovement, Transaction, TransactionItem
from app.inventory.scan_service import line_total, quantize_qty
from app.inventory.schemas import NewProductIn, TransactionIn
from app.products.models import Product, ProductAlias
from app.products.units import UnitConversionError, convert, is_unit_word, normalize_unit
from app.stores.models import Role

MAX_STOCK = Decimal("999999999.999")  # NUMERIC(12,3)
WRITER_ROLES = {Role.MANAGER, Role.SECRETARY}


class ScanAlreadySaved(Conflict):
    """Raised for a scan that is saved. For a repeat of the same request that waited on
    the scan lock, the router returns the first save's result instead."""


def find_existing(db: Session, store_id: UUID, client_request_id: str) -> Transaction | None:
    return db.scalar(
        select(Transaction).where(
            Transaction.store_id == store_id,
            Transaction.client_request_id == client_request_id,
        )
    )


# ---------- alias learning ----------

_PRICE_TAIL = re.compile(r"\s*(@|₱|\bp(?=\s*\d)|\bphp\b).*$")
_LEADING_QTY = re.compile(r"^\s*(\d+(\s+\d+/\d+|[./]\d+)?)\s*(x\s+)?")


def alias_from_raw(raw_text: str) -> str | None:
    """Turn a written row like "2 bx pako 4 @850" into an alias like "pako 4".

    Drops a price part at the end, then a leading quantity and the unit word after it.
    Sizes inside the name ("pako 4", "bakal 10mm") are kept. Returns None when nothing
    useful is left.
    """
    text = " ".join(raw_text.lower().split())
    text = _PRICE_TAIL.sub("", text)
    m = _LEADING_QTY.match(text)
    if m:
        text = text[m.end() :]
        first, _, rest = text.partition(" ")
        if is_unit_word(first):
            text = rest  # "" when the row was only "2 kg"
    text = text.strip(" -,:;.")[:80]
    return text if len(text) >= 2 and not text.replace(" ", "").isdigit() else None


# ---------- the save ----------


@dataclass
class SaveResult:
    transaction: Transaction
    created: bool  # False when this client_request_id was already saved


def _load_scan(db: Session, current: CurrentMember, scan_id: UUID) -> tuple[Scan, list[ScanLine]]:
    scan = db.scalar(
        select(Scan)
        .where(Scan.id == scan_id, Scan.store_id == current.store_id)
        .with_for_update()  # two saves of one scan: the second sees status "saved"
    )
    if scan is None:
        raise NotFound("Scan not found")
    if scan.type != "stock_in":
        raise Conflict("This scan is not a stock-in list")
    if scan.status == "saved":
        raise ScanAlreadySaved("This scan is already saved")
    if scan.status != "read":
        raise Conflict("This scan has not been read yet")
    lines = [ScanLine.model_validate(x) for x in (scan.ai_result_json or {}).get("lines", [])]
    return scan, lines


def _get_or_create_product(db: Session, store_id: UUID, new: NewProductIn) -> Product:
    """Reuse an active product with the same name (ignoring case), else create one.
    A savepoint absorbs the race where another save creates the same name first."""

    def find() -> Product | None:
        return db.scalar(
            select(Product).where(
                Product.store_id == store_id, func.lower(Product.name) == new.name.lower()
            )
        )

    product = find()
    if product is None:
        try:
            with db.begin_nested():
                product = Product(
                    store_id=store_id, name=new.name, category=new.category, base_unit=new.base_unit
                )
                db.add(product)
        except IntegrityError:
            product = find()
            if product is None:
                raise
    if product.archived:
        raise Conflict(f'"{product.name}" is archived. Unarchive it or choose another product.')
    return product


def save_stock_in(db: Session, current: CurrentMember, body: TransactionIn) -> SaveResult:
    """Save a stock-in. Commits on success; on any error nothing is saved.

    Assumes `body` passed schema validation (positive qty, one product choice per line).
    @raises AppError (NotFound/Conflict/Forbidden/Invalid/ScanAlreadySaved) with a message for
        the phone to show; IntegrityError if the same client_request_id won a race
    """
    sid = current.store_id
    existing = find_existing(db, sid, body.client_request_id)
    if existing is not None:
        return SaveResult(existing, created=False)

    if any(line.new_product for line in body.lines) and current.role not in WRITER_ROLES:
        raise Forbidden("Only managers and secretaries can add new products")

    # Check (and lock) the scan before anything is written, so a wrong scan id gets a
    # clear 404 instead of a foreign-key error.
    scan, scan_lines = (None, []) if body.scan_id is None else _load_scan(db, current, body.scan_id)

    # Insert the transaction before touching stock. If the same client_request_id is being
    # saved right now by another request, this INSERT waits for it and then fails on the
    # unique key (the endpoint then returns the first result).
    txn = Transaction(
        store_id=sid,
        type="stock_in",
        client_request_id=body.client_request_id,
        scan_id=body.scan_id,
        created_by=current.user.id,
    )
    db.add(txn)
    db.flush()

    # Resolve each line to a product id (creating new products first).
    product_ids: list[UUID] = []
    for line in body.lines:
        if line.new_product is not None:
            product_ids.append(_get_or_create_product(db, sid, line.new_product).id)
        else:
            assert line.product_id is not None
            product_ids.append(line.product_id)

    # Lock every product row, in id order so two saves can't deadlock each other.
    # populate_existing: refresh objects already in the session (e.g. just created or
    # reused above) with the locked row's values, or stock_qty could be stale.
    locked = {
        p.id: p
        for p in db.scalars(
            select(Product)
            .where(Product.store_id == sid, Product.id.in_(set(product_ids)))
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }

    total = 0
    learned: set[str] = set()
    for no, (line, pid) in enumerate(zip(body.lines, product_ids, strict=True), start=1):
        product = locked.get(pid)
        if product is None:
            raise NotFound(f"Line {no}: product not found")
        if product.archived:
            raise Conflict(f'Line {no}: "{product.name}" is archived')
        try:
            qty_base = quantize_qty(convert(product, line.qty, line.unit))
        except UnitConversionError as e:
            raise Invalid(f"Line {no}: {e}") from None
        if qty_base <= 0:
            raise Invalid(f"Line {no}: quantity is too small for {product.base_unit}")
        new_stock = product.stock_qty + qty_base
        if new_stock > MAX_STOCK:
            raise Invalid(f"Line {no}: stock would be too large")

        amount = line_total(line.qty, line.unit_price_centavos)
        total += amount or 0
        item = TransactionItem(
            store_id=sid,
            transaction_id=txn.id,
            line_no=no,
            product_id=pid,
            # Same 3 decimals the column stores, so the first response and a repeat
            # (read back from the database) are identical.
            qty=quantize_qty(line.qty),
            unit=normalize_unit(line.unit),
            qty_base=qty_base,
            unit_price_centavos=line.unit_price_centavos,
            line_total_centavos=amount,
        )
        db.add(item)
        db.flush()  # item.id for the movement below
        product.stock_qty = new_stock
        db.add(
            StockMovement(
                store_id=sid,
                product_id=pid,
                transaction_id=txn.id,
                transaction_item_id=item.id,
                qty_change=qty_base,
                stock_after=new_stock,
                created_by=current.user.id,
            )
        )

        if line.scan_line is not None and 0 <= line.scan_line < len(scan_lines):
            _learn_alias(db, sid, product, scan_lines[line.scan_line], learned)

    txn.total_centavos = total
    if scan is not None:
        scan.status = "saved"
    db.commit()
    db.refresh(txn)
    return SaveResult(txn, created=True)


def _learn_alias(
    db: Session, store_id: UUID, product: Product, scan_line: ScanLine, learned: set[str]
) -> None:
    """If staff picked a different product than the AI suggested, remember how this item
    was written, so the next scan (and search) matches it. Never takes an alias that
    already belongs to another product."""
    if scan_line.product_id == product.id:
        return  # the AI was right; nothing to learn
    alias = alias_from_raw(scan_line.raw_text)
    if not alias or alias in learned or alias == product.name.lower():
        return
    taken = db.scalar(
        select(ProductAlias.id).where(
            ProductAlias.store_id == store_id, ProductAlias.alias == alias
        )
    )
    if taken is None:
        db.add(ProductAlias(store_id=store_id, product_id=product.id, alias=alias))
        learned.add(alias)
