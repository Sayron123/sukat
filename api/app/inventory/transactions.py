"""Transactions API: save a stock-in (and later sales and adjustments)."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentMemberDep, DbSession
from app.inventory.models import StockMovement, Transaction
from app.inventory.schemas import TransactionIn, TransactionItemOut, TransactionOut
from app.inventory.stock_service import (
    SaveError,
    ScanAlreadySaved,
    find_existing,
    save_stock_in,
)
from app.products.models import Product

router = APIRouter(tags=["transactions"])


def transaction_out(db: DbSession, txn: Transaction) -> TransactionOut:
    """Build the response from what is stored, so a repeat request gets the same answer."""
    pids = {item.product_id for item in txn.items}
    products = {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(pids)))}
    stock_after = dict(
        db.execute(
            select(StockMovement.transaction_item_id, StockMovement.stock_after).where(
                StockMovement.transaction_id == txn.id
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


@router.post("/transactions", response_model=TransactionOut)
def create_transaction(
    body: TransactionIn, response: Response, current: CurrentMemberDep, db: DbSession
) -> TransactionOut:
    """Save a stock-in. Any staff member can save; creating new products needs a
    manager or secretary. 201 on the first save, 200 with the same body on a repeat."""
    try:
        result = save_stock_in(db, current, body)
    except (IntegrityError, ScanAlreadySaved) as e:
        # How a repeat of a request that another request saved at the same moment ends:
        # a unique-key error on client_request_id, or "scan already saved" after waiting
        # on the scan lock. If the first one saved, return its result.
        db.rollback()
        existing = find_existing(db, current.store_id, body.client_request_id)
        if existing is not None:
            return transaction_out(db, existing)
        if isinstance(e, ScanAlreadySaved):
            raise HTTPException(e.status_code, str(e)) from None
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Could not save because of a conflict. Please try again."
        ) from None
    except SaveError as e:
        db.rollback()
        raise HTTPException(e.status_code, str(e)) from None
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return transaction_out(db, result.transaction)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut)
def get_transaction(transaction_id: UUID, current: CurrentMemberDep, db: DbSession):
    txn = db.scalar(
        select(Transaction).where(
            Transaction.id == transaction_id, Transaction.store_id == current.store_id
        )
    )
    if txn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Transaction not found")
    return transaction_out(db, txn)
