"""CSV downloads of the store's data. Managers only (the store's data controller)."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.auth.deps import CurrentMember, DbSession, require_role
from app.exports import service
from app.insights.reports import STORE_TZ
from app.stores.models import Role

router = APIRouter(prefix="/exports", tags=["exports"])

Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]


def _download(name: str, build: Callable[[Session, UUID], str], db: Session, store_id: UUID):
    today = datetime.now(STORE_TZ).date().isoformat()
    return Response(
        content=build(db, store_id).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="sukat-{name}-{today}.csv"',
            "Cache-Control": "no-store",  # store data: never kept by a proxy or browser cache
        },
    )


@router.get("/products")
def export_products(current: Manager, db: DbSession) -> Response:
    """Every product of the store, archived ones too."""
    return _download("products", service.products_csv, db, current.store_id)


@router.get("/transactions")
def export_transactions(current: Manager, db: DbSession) -> Response:
    """Every transaction, one row per line item, oldest first."""
    return _download("transactions", service.transactions_csv, db, current.store_id)


@router.get("/stock-movements")
def export_stock_movements(current: Manager, db: DbSession) -> Response:
    """Every stock change with the stock right after it, oldest first."""
    return _download("stock-movements", service.stock_movements_csv, db, current.store_id)
