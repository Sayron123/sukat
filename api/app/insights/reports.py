"""Reports: sales, best sellers, low stock, stock history, and a stock consistency check.

Plain functions: each takes the database session and the store_id from the caller's
token, filters every query by it, and returns typed Pydantic models (see schemas.py).
The API calls them now; the AI chat (Phase 6) will call the same functions as tools.

Dates are calendar days in the store's time zone (Asia/Manila). They are turned into a
UTC range [start 00:00, day after end 00:00) for queries, because timestamps are stored
in UTC. So a sale at 11:30 PM Manila counts for that day, not the next.

Voided transactions never count in sales numbers.
"""

import math
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import InstrumentedAttribute, Session
from sqlalchemy.sql.elements import ColumnElement

from app.auth.models import User
from app.core.config import settings
from app.core.errors import Invalid, NotFound
from app.insights.schemas import (
    TOP_PRODUCTS_MAX,
    DateRange,
    LowStockItem,
    MovementFilters,
    MovementPage,
    MovementRow,
    PeriodSales,
    SalesSummary,
    ScansToReview,
    ScanToReview,
    StockMismatch,
    TopBy,
    TopProduct,
    TopProducts,
)
from app.inventory.models import Scan, StockMovement, Transaction, TransactionItem
from app.inventory.scan_service import stale_after_seconds
from app.products.constants import PAGE_SIZE
from app.products.models import Product

STORE_TZ = ZoneInfo(settings.STORE_TIMEZONE)
REVIEW_WINDOW_DAYS = 7  # unsaved scans older than this no longer count as "to review"
# At most this many scans to review are returned; `has_more` says whether there were more.
REVIEW_LIST_MAX = 50


# ---------- dates ----------


def store_today(now: datetime | None = None) -> date:
    """Today's date in the store's time zone. @param now: for tests (aware datetime)."""
    return (now or datetime.now(UTC)).astimezone(STORE_TZ).date()


def utc_bounds(period: DateRange) -> tuple[datetime, datetime]:
    """[start, end) in UTC for the Manila days of `period`, both days included.

    Example: 2026-11-05..2026-11-05 -> 2026-11-04 16:00 UTC to 2026-11-05 16:00 UTC.
    """
    start = datetime.combine(period.start, time.min, STORE_TZ)
    end = datetime.combine(period.end + timedelta(days=1), time.min, STORE_TZ)
    return start.astimezone(UTC), end.astimezone(UTC)


def make_range(start: date | None, end: date | None, default_today: bool) -> DateRange | None:
    """Build a DateRange from optional query values.

    Neither given: today (when default_today) or None (no date filter). One given: that
    single day.
    @raises Invalid for end before start or a range over 366 days
    """
    if start is None and end is None:
        if not default_today:
            return None
        start = end = store_today()
    try:
        return DateRange(start=start or end, end=end or start)  # type: ignore[arg-type]
    except ValidationError as e:
        raise Invalid(e.errors()[0]["msg"].removeprefix("Value error, ")) from None


def _in_range(column: InstrumentedAttribute[datetime], period: DateRange) -> ColumnElement[bool]:
    lo, hi = utc_bounds(period)
    return and_(column >= lo, column < hi)


def _pages(total: int) -> int:
    return max(1, math.ceil(total / PAGE_SIZE))


# ---------- sales ----------


def _saved_sales(store_id: UUID) -> list[ColumnElement[bool]]:
    return [
        Transaction.store_id == store_id,
        Transaction.type == "sale",
        Transaction.status == "saved",  # voided sales never count
    ]


def _period_sales(
    db: Session, store_id: UUID, period: DateRange, until: datetime | None = None
) -> PeriodSales:
    """Saved sales in `period`; with `until`, only those before that moment."""
    where = [*_saved_sales(store_id), _in_range(Transaction.created_at, period)]
    if until is not None:
        where.append(Transaction.created_at < until)
    total, count = db.execute(
        select(func.coalesce(func.sum(Transaction.total_centavos), 0), func.count()).where(*where)
    ).one()
    return PeriodSales(range=period, until=until, total_centavos=int(total), sales_count=int(count))


def _comparison(period: DateRange, today: date) -> tuple[DateRange, bool, str]:
    """The period to compare `period` with, whether it is still running, and how to
    describe the comparison (shown under the number on Home).

    A finished period is compared with the period of the same length just before it.
    A period that includes today is lined up with the calendar instead:
    - one day (today): yesterday, "same time yesterday"
    - a week from Monday: last week from Monday, "same time last week"
    - a month from the 1st: last month from the 1st (cut at its last day), "same time
      last month"
    - anything else: the same number of days just before
    The caller then cuts the previous period at the same elapsed time, so Mon-Wed 9:15
    AM is compared with last Mon-Wed 9:15 AM.
    """
    running = period.start <= today <= period.end
    if not running:
        what = "the day before" if period.days == 1 else f"the previous {period.days} days"
        return period.previous(), False, what

    if period.days == 1:
        return period.previous(), True, "same time yesterday"
    if period.start.weekday() == 0 and period.days <= 7:
        week = timedelta(days=7)
        before = DateRange.model_construct(start=period.start - week, end=period.end - week)
        return before, True, "same time last week"
    if period.start.day == 1 and (period.end.year, period.end.month) == (
        period.start.year,
        period.start.month,
    ):
        last_month_end = period.start - timedelta(days=1)
        start = last_month_end.replace(day=1)
        end = min(start + (period.end - period.start), last_month_end)
        return DateRange.model_construct(start=start, end=end), True, "same time last month"
    return period.previous(), True, f"same point in the previous {period.days} days"


def sales_summary(
    db: Session, store_id: UUID, period: DateRange, now: datetime | None = None
) -> SalesSummary:
    """Total and number of sales in `period`, compared with an earlier period (see
    `_comparison`; `compared_to` in the result says which, in words).

    When `period` includes today it isn't over yet, so the previous period is cut at the
    same elapsed time: today 00:00-09:15 is compared with yesterday 00:00-09:15, not
    with all of yesterday (which would show a drop every morning), and this week so far
    with last week up to the same weekday and time. Finished periods are compared whole.

    @param now: for tests (aware datetime); defaults to the current time
    @returns change_pct rounded to 1 decimal, or None when the previous total was 0
    """
    now = now or datetime.now(UTC)
    before, running, compared_to = _comparison(period, store_today(now))
    until = None
    if running:
        elapsed = now - utc_bounds(period)[0]
        until = utc_bounds(before)[0] + elapsed
    current = _period_sales(db, store_id, period)
    previous = _period_sales(db, store_id, before, until)
    change = (
        round((current.total_centavos - previous.total_centavos) * 100 / previous.total_centavos, 1)
        if previous.total_centavos
        else None
    )
    return SalesSummary(
        range=period,
        total_centavos=current.total_centavos,
        sales_count=current.sales_count,
        previous=previous,
        compared_to=compared_to,
        change_pct=change,
    )


def top_products(
    db: Session, store_id: UUID, period: DateRange, limit: int = 10, by: TopBy = "qty"
) -> TopProducts:
    """Best-selling products in `period`, by quantity sold (base unit) or by revenue.

    @param limit 1..50
    """
    limit = max(1, min(limit, TOP_PRODUCTS_MAX))
    qty = func.sum(TransactionItem.qty_base)
    revenue = func.coalesce(func.sum(TransactionItem.line_total_centavos), 0)
    rows = db.execute(
        select(
            Product.id,
            Product.name,
            Product.base_unit,
            qty,
            revenue,
            func.count(func.distinct(TransactionItem.transaction_id)),
        )
        .join(
            Transaction,
            and_(
                Transaction.id == TransactionItem.transaction_id,
                Transaction.store_id == TransactionItem.store_id,
            ),
        )
        .join(
            Product,
            and_(Product.id == TransactionItem.product_id, Product.store_id == store_id),
        )
        .where(
            TransactionItem.store_id == store_id,
            *_saved_sales(store_id),
            _in_range(Transaction.created_at, period),
        )
        .group_by(Product.id, Product.name, Product.base_unit)
        .order_by((qty if by == "qty" else revenue).desc(), func.lower(Product.name))
        .limit(limit)
    ).all()
    return TopProducts(
        range=period,
        by=by,
        items=[
            TopProduct(
                product_id=pid,
                name=name,
                base_unit=unit,
                qty=q,
                revenue_centavos=int(rev or 0),
                sales_count=int(n or 0),
            )
            for pid, name, unit, q, rev, n in rows
        ],
    )


# ---------- stock ----------


def low_stock(db: Session, store_id: UUID) -> list[LowStockItem]:
    """Active products at or below their low-stock level, lowest stock first.
    Products without a level are never "low"."""
    rows = db.scalars(
        select(Product)
        .where(
            Product.store_id == store_id,
            Product.archived.is_(False),
            Product.low_stock_level.is_not(None),
            Product.stock_qty <= Product.low_stock_level,
        )
        .order_by(Product.stock_qty, func.lower(Product.name))
    ).all()
    return [
        LowStockItem(
            product_id=p.id,
            name=p.name,
            category=p.category,
            base_unit=p.base_unit,
            stock_qty=p.stock_qty,
            low_stock_level=p.low_stock_level or Decimal(0),
        )
        for p in rows
    ]


_KIND = case((StockMovement.is_reversal, "void"), else_=Transaction.type)


def stock_movements(db: Session, store_id: UUID, filters: MovementFilters) -> MovementPage:
    """Stock movements, newest first, 20 per page. Every filter is optional:
    a date range, one product, a kind (sale / stock_in / adjustment / void), or the
    staff member who made them."""
    where: list[ColumnElement[bool]] = [StockMovement.store_id == store_id]
    if filters.range is not None:
        where.append(_in_range(StockMovement.created_at, filters.range))
    if filters.product_id is not None:
        where.append(StockMovement.product_id == filters.product_id)
    if filters.kind == "void":
        where.append(StockMovement.is_reversal.is_(True))
    elif filters.kind is not None:
        where += [StockMovement.is_reversal.is_(False), Transaction.type == filters.kind]
    if filters.created_by is not None:
        where.append(StockMovement.created_by == filters.created_by)

    txn_join = and_(
        Transaction.id == StockMovement.transaction_id,
        Transaction.store_id == StockMovement.store_id,
    )
    total = (
        db.scalar(
            select(func.count())
            .select_from(StockMovement)
            .join(Transaction, txn_join)
            .where(*where)
        )
        or 0
    )
    rows = db.execute(
        select(StockMovement, _KIND, Product.name, Product.base_unit, User.full_name)
        .join(Transaction, txn_join)
        .join(
            Product,
            and_(
                Product.id == StockMovement.product_id, Product.store_id == StockMovement.store_id
            ),
        )
        .outerjoin(User, User.id == StockMovement.created_by)
        .where(*where)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .offset((filters.page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
    ).all()
    return MovementPage(
        items=[
            MovementRow(
                id=m.id,
                created_at=m.created_at,
                product_id=m.product_id,
                product_name=name,
                base_unit=unit,
                qty_change=m.qty_change,
                stock_after=m.stock_after,
                kind=kind,
                transaction_id=m.transaction_id,
                created_by=m.created_by,
                created_by_name=who,
            )
            for m, kind, name, unit, who in rows
        ],
        total=total,
        page=filters.page,
        page_size=PAGE_SIZE,
        pages=_pages(total),
    )


def product_history(
    db: Session, store_id: UUID, product_id: UUID, period: DateRange | None = None, page: int = 1
) -> MovementPage:
    """One product's movements with stock_after, newest first, 20 per page.

    @raises NotFound for a product of another store (or none)
    """
    exists = db.scalar(
        select(Product.id).where(Product.id == product_id, Product.store_id == store_id)
    )
    if exists is None:
        raise NotFound("Product not found")
    return stock_movements(
        db, store_id, MovementFilters(range=period, product_id=product_id, page=page)
    )


def stock_check(db: Session, store_id: UUID) -> list[StockMismatch]:
    """Products whose stock_qty differs from the sum of their stock movements.

    Stock only changes together with a movement in the same database transaction, so
    this list should always be empty. Anything here means a bug or a manual edit.
    """
    sums = (
        select(
            StockMovement.product_id.label("pid"),
            func.sum(StockMovement.qty_change).label("total"),
        )
        .where(StockMovement.store_id == store_id)
        .group_by(StockMovement.product_id)
        .subquery()
    )
    moved = func.coalesce(sums.c.total, 0)
    rows = db.execute(
        select(Product.id, Product.name, Product.stock_qty, moved)
        .outerjoin(sums, sums.c.pid == Product.id)
        .where(Product.store_id == store_id, Product.stock_qty != moved)
        .order_by(func.lower(Product.name))
    ).all()
    return [
        StockMismatch(
            product_id=pid,
            name=name,
            stock_qty=qty,
            movements_sum=Decimal(total),
            difference=qty - Decimal(total),
        )
        for pid, name, qty, total in rows
    ]


# ---------- scans ----------


def scans_to_review(db: Session, store_id: UUID, now: datetime | None = None) -> ScansToReview:
    """Photos from the last 7 days that were read but not saved, or whose read failed in
    a way "Try again" can fix, newest first (max 50, `has_more` if there were more).
    Both mean a paper list that isn't recorded yet. Older unsaved scans are treated as
    abandoned.

    Failed means: the AI said retrying may help, or a read stuck in "pending" (cut off,
    e.g. by a server restart), which the phone also shows as a failure to retry. A
    failure retrying can't fix isn't listed: there is nothing to do with it.
    """
    now = now or datetime.now(UTC)
    since = now - timedelta(days=REVIEW_WINDOW_DAYS)
    stuck_before = now - timedelta(seconds=stale_after_seconds())
    retryable = Scan.ai_result_json["retryable"].as_boolean().is_(True)
    rows = db.execute(
        select(Scan, User.full_name)
        .outerjoin(User, User.id == Scan.created_by)
        .where(
            Scan.store_id == store_id,
            or_(
                Scan.status == "read",
                and_(Scan.status == "failed", retryable),
                and_(Scan.status == "pending", Scan.updated_at < stuck_before),
            ),
            Scan.created_at >= since,
        )
        .order_by(Scan.created_at.desc(), Scan.id.desc())
        .limit(REVIEW_LIST_MAX + 1)  # one extra row only to learn whether there are more
    ).all()
    items = [
        ScanToReview(
            scan_id=s.id,
            type=s.type,
            status="read" if s.status == "read" else "failed",
            line_count=len((s.ai_result_json or {}).get("lines", [])),
            created_at=s.created_at,
            created_by_name=who,
        )
        for s, who in rows[:REVIEW_LIST_MAX]
    ]
    return ScansToReview(items=items, has_more=len(rows) > REVIEW_LIST_MAX)
