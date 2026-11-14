"""Saving stock-ins and sales: one database transaction that records the lines and
updates stock (up for stock in, down for a sale).

Guarantees:
- Idempotent: the same client_request_id saves once; repeats get the first result.
- No lost updates: product rows are locked (SELECT ... FOR UPDATE) before stock changes,
  so two saves at the same moment both count.
- All or nothing: any error rolls back every row of the save.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.schemas import ScanLine
from app.auth.deps import CurrentMember
from app.auth.models import User
from app.core.errors import AppError, Conflict, Forbidden, Invalid, NotFound
from app.insights.reports import utc_bounds
from app.insights.schemas import DateRange
from app.inventory.models import Scan, StockMovement, Transaction, TransactionItem
from app.inventory.scan_service import IN_TRASH_MESSAGE, line_total, quantize_qty
from app.inventory.schemas import (
    NewProductIn,
    TransactionIn,
    TransactionItemOut,
    TransactionOut,
    TransactionSummaryOut,
)
from app.products.constants import PAGE_SIZE
from app.products.models import Product, ProductAlias
from app.products.pricing import priced_line
from app.products.units import UnitConversionError, convert, is_unit_word, normalize_unit
from app.stores.models import Role

MAX_STOCK = Decimal("999999999.999")  # NUMERIC(12,3) limit, both directions
WRITER_ROLES = {Role.MANAGER, Role.SECRETARY}


class NegativeStock(Conflict):
    """A sale would take some stock below 0. The client shows the list and can resend
    with confirm=true (same client_request_id: nothing was saved)."""

    code = "negative_stock"


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
    return _clean_alias(text)


def _clean_alias(text: str) -> str | None:
    text = " ".join(text.lower().split()).strip(" -,:;.")[:80]
    return text if len(text) >= 2 and not text.replace(" ", "").isdigit() else None


def scan_line_alias(scan_line: ScanLine) -> str | None:
    if scan_line.item_text is None:
        return alias_from_raw(scan_line.raw_text)
    return _clean_alias(scan_line.item_text)


# ---------- the save ----------


@dataclass
class SaveResult:
    transaction: Transaction
    created: bool  # False when this client_request_id was already saved


def _load_scan(
    db: Session, current: CurrentMember, scan_id: UUID, txn_type: str
) -> tuple[Scan, list[ScanLine]]:
    scan = db.scalar(
        select(Scan)
        .where(Scan.id == scan_id, Scan.store_id == current.store_id)
        .with_for_update()  # two saves of one scan: the second sees status "saved"
    )
    if scan is None:
        raise NotFound("Scan not found")
    if scan.deleted_at is not None:
        raise NotFound(IN_TRASH_MESSAGE)
    if scan.type != txn_type:
        kind = "sale receipt" if scan.type == "sale" else "stock-in list"
        raise Conflict(f"This scan is a {kind}")
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


def save_transaction(db: Session, current: CurrentMember, body: TransactionIn) -> SaveResult:
    """Save a stock-in (adds stock) or a sale (removes stock). Commits on success; on any
    error nothing is saved.

    Sale rules: existing products only (checked by the schema); a line without a price
    uses the product's price for that unit; if any product's stock would go below 0,
    NegativeStock is raised unless body.confirm is true.

    Assumes `body` passed schema validation (positive qty, one product choice per line).
    @raises AppError (NotFound/Conflict/Forbidden/Invalid/NegativeStock/ScanAlreadySaved)
        with a message for the phone to show; IntegrityError if the same
        client_request_id won a race
    """
    sid = current.store_id
    is_sale = body.type == "sale"
    sign = -1 if is_sale else 1
    existing = find_existing(db, sid, body.client_request_id)
    if existing is not None:
        return SaveResult(existing, created=False)

    if any(line.new_product for line in body.lines) and current.role not in WRITER_ROLES:
        raise Forbidden("Only managers and secretaries can add new products")

    # Check (and lock) the scan before anything is written, so a wrong scan id gets a
    # clear 404 instead of a foreign-key error.
    scan, scan_lines = (
        (None, []) if body.scan_id is None else _load_scan(db, current, body.scan_id, body.type)
    )

    # Insert the transaction before touching stock. If the same client_request_id is being
    # saved right now by another request, this INSERT waits for it and then fails on the
    # unique key (the endpoint then returns the first result).
    txn = Transaction(
        store_id=sid,
        type=body.type,
        client_request_id=body.client_request_id,
        scan_id=body.scan_id,
        created_by=current.user.id,
    )
    db.add(txn)
    db.flush()

    # Resolve each line to a product id (creating new products first; stock-in only).
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
    stock_before = {pid: p.stock_qty for pid, p in locked.items()}

    total = 0
    learned: set[str] = set()
    # Aliases change how every later scan and search matches, like editing a product, so
    # only managers and secretaries teach them. A member's save still goes through.
    can_learn = current.role in WRITER_ROLES
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
        change = sign * qty_base
        new_stock = product.stock_qty + change
        if abs(new_stock) > MAX_STOCK:
            raise Invalid(f"Line {no}: stock would be out of range")

        unit_price = line.unit_price_centavos
        if is_sale and unit_price is None:
            unit_price, amount = priced_line(product, product.price_centavos, line.qty, line.unit)
        else:
            amount = line_total(line.qty, unit_price)  # written price, used as written
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
            unit_price_centavos=unit_price,
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
                qty_change=change,
                stock_after=new_stock,
                created_by=current.user.id,
            )
        )

        if can_learn and line.scan_line is not None and 0 <= line.scan_line < len(scan_lines):
            _learn_alias(db, sid, product, scan_lines[line.scan_line], learned)

    if is_sale and not body.confirm:
        short = [p for pid, p in locked.items() if p.stock_qty < 0]
        if short:
            raise NegativeStock(
                "Some stock would go below 0. Check the quantities, or confirm to save anyway.",
                extra={
                    "products": [
                        {
                            "product_id": str(p.id),
                            "name": p.name,
                            "base_unit": p.base_unit,
                            "stock": str(stock_before[p.id]),
                            "stock_after": str(p.stock_qty),
                        }
                        for p in sorted(short, key=lambda p: p.name.lower())
                    ]
                },
            )

    txn.total_centavos = total
    if scan is not None:
        scan.status = "saved"
    db.commit()
    db.refresh(txn)
    return SaveResult(txn, created=True)


def _learn_alias(
    db: Session, store_id: UUID, product: Product, scan_line: ScanLine, learned: set[str]
) -> None:
    """If staff picked a different product than the scan suggested, or kept a product
    the AI match step found, remember how this item was written, so the next scan (and
    search) matches it by code. Never takes an alias that already belongs to another
    product."""
    if scan_line.product_id == product.id and scan_line.matched_by != "ai":
        return
    alias = scan_line_alias(scan_line)
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


# ---------- used by the router ----------


def save_transaction_once(db: Session, current: CurrentMember, body: TransactionIn) -> SaveResult:
    """save_transaction, plus the concurrent-repeat case: when the same request is being
    saved by another request at the same moment, this one ends with a unique-key error
    on client_request_id (or "scan already saved" after waiting on the scan lock). If
    the other one saved, return its result (created=False) instead of an error.

    @raises AppError subclasses as save_transaction; Conflict if the race can't be resolved
    """
    try:
        return save_transaction(db, current, body)
    except (IntegrityError, ScanAlreadySaved) as e:
        db.rollback()
        existing = find_existing(db, current.store_id, body.client_request_id)
        if existing is not None:
            return SaveResult(existing, created=False)
        if isinstance(e, ScanAlreadySaved):
            raise
        raise Conflict("Could not save because of a conflict. Please try again.") from None
    except AppError:
        # Refused (e.g. negative_stock). Must come after the clause above, because
        # ScanAlreadySaved is an AppError too. Roll back now so the transaction row and
        # product locks are released before the phone resends with confirm=true,
        # instead of whenever the request's session gets closed.
        db.rollback()
        raise


def get_transaction(db: Session, store_id: UUID, transaction_id: UUID) -> Transaction:
    """@raises NotFound also for another store's transaction"""
    txn = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.store_id == store_id
        )
    )
    if txn is None:
        raise NotFound("Transaction not found")
    return txn


def transaction_view(db: Session, txn: Transaction) -> TransactionOut:
    """Built from what is stored, so a repeated request gets exactly the same answer.
    `stock_after` per line is from the original movement (not the void reversal)."""
    pids = {item.product_id for item in txn.items}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(pids)))}
    stock_after = dict(
        db.execute(
            select(StockMovement.transaction_item_id, StockMovement.stock_after).where(
                StockMovement.transaction_id == txn.id, StockMovement.is_reversal.is_(False)
            )
        ).all()
    )
    names = dict(
        db.execute(
            select(User.id, User.full_name).where(
                User.id.in_({u for u in (txn.created_by, txn.voided_by) if u})
            )
        ).all()
    )
    return TransactionOut(
        id=txn.id,
        type=txn.type,
        status=txn.status,
        client_request_id=txn.client_request_id,
        scan_id=txn.scan_id,
        total_centavos=txn.total_centavos,
        created_at=txn.created_at,
        created_by_name=names.get(txn.created_by) if txn.created_by else None,
        voided_at=txn.voided_at,
        voided_by_name=names.get(txn.voided_by) if txn.voided_by else None,
        items=[
            TransactionItemOut(
                line_no=item.line_no,
                product_id=item.product_id,
                product_name=products[item.product_id].name,
                base_unit=products[item.product_id].base_unit,
                qty=item.qty,
                unit=item.unit,
                qty_base=item.qty_base,
                unit_price_centavos=item.unit_price_centavos,
                line_total_centavos=item.line_total_centavos,
                stock_after=stock_after[item.id],
            )
            for item in txn.items
        ],
    )


def list_transactions(
    db: Session,
    store_id: UUID,
    txn_type: str | None,
    page: int,
    period: DateRange | None = None,
) -> tuple[list[TransactionSummaryOut], int]:
    """One page (newest first) of this store's transactions, plus the total count.
    `period` is Manila calendar days (see app/insights/reports.py)."""
    where = [Transaction.store_id == store_id]
    if txn_type:
        where.append(Transaction.type == txn_type)
    if period is not None:
        lo, hi = utc_bounds(period)
        where += [Transaction.created_at >= lo, Transaction.created_at < hi]
    total = db.scalar(select(func.count()).select_from(Transaction).where(*where)) or 0
    item_count = (
        select(func.count())
        .where(TransactionItem.transaction_id == Transaction.id)
        .correlate(Transaction)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Transaction, item_count)
        .where(*where)
        .order_by(Transaction.created_at.desc(), Transaction.id.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    return [
        TransactionSummaryOut(
            id=t.id,
            type=t.type,
            status=t.status,
            total_centavos=t.total_centavos,
            item_count=count,
            created_at=t.created_at,
        )
        for t, count in rows
    ], total


# ---------- void ----------


class AlreadyVoided(Conflict):
    code = "already_voided"


def void_transaction(db: Session, current: CurrentMember, transaction_id: UUID) -> Transaction:
    """Undo a saved transaction without deleting anything, in ONE database transaction:
    status becomes "voided" (with who and when), and every stock movement it made gets
    a reversing movement (a sale's stock comes back; a stock-in's goes out again).

    Stock may go below 0 when voiding a stock-in whose items were already sold; that is
    the true count, so it isn't blocked.

    Assumes the caller checked the role (manager/secretary).
    @raises NotFound (also for another store's transaction), AlreadyVoided
    """
    # Lock the transaction first: a second void at the same moment waits here, then
    # sees "voided". (The unique (transaction_item_id, is_reversal) key is a backstop.)
    txn = db.scalar(
        select(Transaction)
        .where(Transaction.id == transaction_id, Transaction.store_id == current.store_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if txn is None:
        raise NotFound("Transaction not found")
    if txn.status == "voided":
        db.rollback()  # release the row lock right away
        raise AlreadyVoided("This transaction is already voided")

    movements = list(
        db.scalars(
            select(StockMovement).where(
                StockMovement.transaction_id == txn.id, StockMovement.is_reversal.is_(False)
            )
        )
    )
    # Same lock order as saving (product id), so a void and a sale can't deadlock.
    products = {
        p.id: p
        for p in db.scalars(
            select(Product)
            .where(
                Product.store_id == current.store_id,
                Product.id.in_({m.product_id for m in movements}),
            )
            .order_by(Product.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    for m in sorted(movements, key=lambda m: (m.product_id, m.id)):
        product = products[m.product_id]
        new_stock = product.stock_qty - m.qty_change
        if abs(new_stock) > MAX_STOCK:
            raise Invalid(f'Voiding would put "{product.name}" stock out of range')
        product.stock_qty = new_stock
        db.add(
            StockMovement(
                store_id=txn.store_id,
                product_id=m.product_id,
                transaction_id=txn.id,
                transaction_item_id=m.transaction_item_id,
                is_reversal=True,
                qty_change=-m.qty_change,
                stock_after=new_stock,
                created_by=current.user.id,
            )
        )

    txn.status = "voided"
    txn.voided_at = datetime.now(UTC)
    txn.voided_by = current.user.id
    db.commit()
    db.refresh(txn)
    return txn
