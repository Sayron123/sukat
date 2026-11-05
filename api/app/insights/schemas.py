"""Typed inputs and outputs of the report functions.

The same shapes are returned by the API and will be used as tool inputs/outputs by the
AI chat (Phase 6), so every field is explicit and documented.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

MAX_RANGE_DAYS = 366
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
        """The period of the same length just before this one (today -> yesterday)."""
        return DateRange(
            start=self.start - timedelta(days=self.days), end=self.start - timedelta(days=1)
        )


# ---------- sales ----------


class PeriodSales(BaseModel):
    range: DateRange
    total_centavos: int  # sum of saved (not voided) sales
    sales_count: int


class SalesSummary(BaseModel):
    range: DateRange
    total_centavos: int
    sales_count: int
    previous: PeriodSales  # same length, just before `range`
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
    """A photo that was read but not saved yet."""

    scan_id: UUID
    type: Literal["sale", "stock_in"]
    line_count: int
    created_at: datetime
    created_by_name: str | None
