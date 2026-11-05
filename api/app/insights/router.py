"""Report endpoints: thin wrappers around app/insights/reports.py.

Dates are Manila calendar days (YYYY-MM-DD), both included. Who can read what:
- any staff member: sales summary, low stock, stock history, scans to review
- managers and secretaries: top products
- managers only: stock check
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.auth.deps import CurrentMember, CurrentMemberDep, DbSession, require_role
from app.insights import reports
from app.insights.schemas import (
    TOP_PRODUCTS_MAX,
    LowStockItem,
    MovementFilters,
    MovementKind,
    MovementPage,
    SalesSummary,
    ScanToReview,
    StockMismatch,
    TopBy,
    TopProducts,
)
from app.stores.models import Role

router = APIRouter(prefix="/reports", tags=["reports"])

Writer = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]
Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]
Start = Annotated[date | None, Query(description="First day (Manila), YYYY-MM-DD")]
End = Annotated[date | None, Query(description="Last day (Manila), included")]
Page = Annotated[int, Query(ge=1, le=10_000)]


@router.get("/sales-summary", response_model=SalesSummary)
def sales_summary(
    current: CurrentMemberDep, db: DbSession, start: Start = None, end: End = None
) -> SalesSummary:
    """Sales total and count (voided excluded), with the previous period of the same
    length. Defaults to today."""
    period = reports.make_range(start, end, default_today=True)
    assert period is not None
    return reports.sales_summary(db, current.store_id, period)


@router.get("/top-products", response_model=TopProducts)
def top_products(
    current: Writer,
    db: DbSession,
    start: Start = None,
    end: End = None,
    limit: Annotated[int, Query(ge=1, le=TOP_PRODUCTS_MAX)] = 10,
    by: TopBy = "qty",
) -> TopProducts:
    """Best sellers by quantity or revenue (manager or secretary). Defaults to today."""
    period = reports.make_range(start, end, default_today=True)
    assert period is not None
    return reports.top_products(db, current.store_id, period, limit, by)


@router.get("/low-stock", response_model=list[LowStockItem])
def low_stock(current: CurrentMemberDep, db: DbSession) -> list[LowStockItem]:
    """Products at or below their low-stock level, lowest first."""
    return reports.low_stock(db, current.store_id)


@router.get("/stock-movements", response_model=MovementPage)
def stock_movements(
    current: CurrentMemberDep,
    db: DbSession,
    start: Start = None,
    end: End = None,
    product_id: UUID | None = None,
    kind: MovementKind | None = None,
    created_by: UUID | None = None,
    page: Page = 1,
) -> MovementPage:
    """Every stock change, newest first, 20 per page. No dates = all time."""
    filters = MovementFilters(
        range=reports.make_range(start, end, default_today=False),
        product_id=product_id,
        kind=kind,
        created_by=created_by,
        page=page,
    )
    return reports.stock_movements(db, current.store_id, filters)


@router.get("/products/{product_id}/history", response_model=MovementPage)
def product_history(
    product_id: UUID,
    current: CurrentMemberDep,
    db: DbSession,
    start: Start = None,
    end: End = None,
    page: Page = 1,
) -> MovementPage:
    """One product's movements with stock after each, newest first. 404 for another
    store's product."""
    period = reports.make_range(start, end, default_today=False)
    return reports.product_history(db, current.store_id, product_id, period, page)


@router.get("/stock-check", response_model=list[StockMismatch])
def stock_check(current: Manager, db: DbSession) -> list[StockMismatch]:
    """Products whose stock doesn't match their movements (manager only). Should be
    empty; anything listed needs investigating."""
    return reports.stock_check(db, current.store_id)


@router.get("/scans-to-review", response_model=list[ScanToReview])
def scans_to_review(current: CurrentMemberDep, db: DbSession) -> list[ScanToReview]:
    """Photos read in the last 7 days but not saved yet, newest first."""
    return reports.scans_to_review(db, current.store_id)
