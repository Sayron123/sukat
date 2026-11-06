"""Typed inputs and outputs of the report functions.

The same shapes are returned by the API and will be used as tool inputs/outputs by the
AI chat (Phase 6), so every field is explicit and documented.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

MAX_RANGE_DAYS = 366
# Dates outside these are refused. Year 1 or 9999 would overflow when turned into UTC
# (or into the previous period), and no store has records that old or that far ahead.
MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)
TOP_PRODUCTS_MAX = 50

# What caused a stock movement: the transaction's type, or "void" for a movement that
# undoes a line of a voided transaction.
MovementKind = Literal["sale", "stock_in", "adjustment", "void"]
TopBy = Literal["qty", "revenue"]


class DateRange(BaseModel):
    """Calendar days in the store's time zone (Asia/Manila), both ends included.

    Example: start=end=2026-11-05 means 2026-11-05 00:00 to 23:59:59 Manila time.
    """

    start: date
    end: date

    @field_validator("start", "end")
    @classmethod
    def _in_bounds(cls, day: date) -> date:
        # A field validator (not the model one below) so that previous(), which may start
        # before MIN_DATE, still passes when nested in PeriodSales: Pydantic re-runs
        # "after" model validators on nested instances, but not field validators.
        if not MIN_DATE <= day <= MAX_DATE:
            raise ValueError(f"dates must be between {MIN_DATE} and {MAX_DATE}")
        return day

    @model_validator(mode="after")
    def _check(self) -> "DateRange":
        if self.end < self.start:
            raise ValueError("end must be on or after start")
        if self.days > MAX_RANGE_DAYS:
            raise ValueError(f"a range can be at most {MAX_RANGE_DAYS} days")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def previous(self) -> "DateRange":
        """The period of the same length just before this one (today -> yesterday).

        Built without validation: before the earliest allowed range it starts in 1999,
        which is fine to query (it just has no sales) and to return.
        """
        return DateRange.model_construct(
            start=self.start - timedelta(days=self.days), end=self.start - timedelta(days=1)
        )


# ---------- sales ----------


class PeriodSales(BaseModel):
    range: DateRange
    # Only sales before this moment (UTC) count; None = the whole range. Set on the
    # previous period when the current one isn't over yet (it includes today).
    until: datetime | None = None
    total_centavos: int  # sum of saved (not voided) sales
    sales_count: int


class SalesSummary(BaseModel):
    range: DateRange
    total_centavos: int
    sales_count: int
    # What `range` is compared with. Finished: the same number of days just before.
    # Includes today: lined up with the calendar (yesterday, last week from Monday, last
    # month from the 1st) and cut at the same elapsed time (`previous.until`), so at
    # 9:15 AM today is compared with yesterday until 9:15 AM.
    previous: PeriodSales
    # The comparison in words, for the screen: "same time yesterday", "same time last
    # week", "same time last month", "the day before", "the previous 7 days", ...
    compared_to: str
    # Percent change of total_centavos vs previous, 1 decimal. None when previous was 0.
    change_pct: float | None


class TopProduct(BaseModel):
    product_id: UUID
    name: str
    base_unit: str
    qty: Decimal  # sold, in the base unit
    revenue_centavos: int  # sum of known line totals
    sales_count: int  # number of sales that included it


class TopProducts(BaseModel):
    range: DateRange
    by: TopBy
    items: list[TopProduct]


# ---------- stock ----------


class LowStockItem(BaseModel):
    product_id: UUID
    name: str
    category: str
    base_unit: str
    stock_qty: Decimal
    low_stock_level: Decimal


class MovementFilters(BaseModel):
    """Filters for stock_movements. All optional; page is 1-based (20 rows per page)."""

    range: DateRange | None = None
    product_id: UUID | None = None
    kind: MovementKind | None = None
    created_by: UUID | None = None
    page: int = Field(default=1, ge=1, le=10_000)


class MovementRow(BaseModel):
    id: UUID
    created_at: datetime
    product_id: UUID
    product_name: str
    base_unit: str
    qty_change: Decimal  # + into stock, - out of stock (base unit)
    stock_after: Decimal
    kind: MovementKind
    transaction_id: UUID
    created_by: UUID
    created_by_name: str | None


class MovementPage(BaseModel):
    items: list[MovementRow]
    total: int
    page: int
    page_size: int
    pages: int


class StockMismatch(BaseModel):
    """A product whose stock_qty is not the sum of its movements (should never happen)."""

    product_id: UUID
    name: str
    stock_qty: Decimal
    movements_sum: Decimal
    difference: Decimal  # stock_qty - movements_sum


# ---------- scans ----------


class ScanToReview(BaseModel):
    """A photo that was read but not saved yet, or that couldn't be read."""

    scan_id: UUID
    type: Literal["sale", "stock_in"]
    status: Literal["read", "failed"]  # failed = the AI couldn't read it; can be retried
    line_count: int  # 0 for a failed read
    created_at: datetime
    created_by_name: str | None


class ScansToReview(BaseModel):
    """The newest scans to review, at most REVIEW_LIST_MAX (50) of them."""

    items: list[ScanToReview]
    has_more: bool  # True when older ones were left out, so the screen can say "50+"
