"""Inventory HTTP endpoints: photo upload, scans, and transactions.

Thin: check access, call scan_service / stock_service, shape the response.
"""

import math
from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.ai.base import VisionReader
from app.ai.provider import get_backup_vision_reader, get_vision_reader
from app.auth.deps import (
    CurrentMember,
    CurrentMemberDep,
    DbSession,
    VerifiedMemberDep,
    require_role,
)
from app.core.config import settings
from app.core.errors import AppError, BadRequest, Forbidden, NotFound
from app.core.storage import LocalStorage, Storage, get_storage
from app.insights import reports
from app.inventory import scan_service, stock_service
from app.inventory.scan_service import PHOTO_KEY_RE
from app.inventory.schemas import (
    ScanIn,
    ScanOut,
    TransactionIn,
    TransactionOut,
    TransactionPage,
    UploadUrlIn,
    UploadUrlOut,
)
from app.products.constants import PAGE_SIZE
from app.stores.models import Role

router = APIRouter()

StorageDep = Annotated[Storage, Depends(get_storage)]
# Voiding is limited to managers and secretaries; everyone can scan and save.
Writer = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]
ReaderDep = Annotated[VisionReader, Depends(get_vision_reader)]
BackupReaderDep = Annotated[VisionReader | None, Depends(get_backup_vision_reader)]


# ---------- photo upload ----------


@router.post("/scans/upload-url", response_model=UploadUrlOut, tags=["scans"])
def create_upload_url(body: UploadUrlIn, current: CurrentMemberDep, storage: StorageDep):
    """A presigned PUT URL for one list photo. Any staff member can upload."""
    if body.size_bytes > settings.UPLOAD_MAX_BYTES:
        raise AppError(
            f"Photo is too large (max {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB)",
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
        )
    key = scan_service.new_photo_key(current.store_id, body.content_type)
    up = storage.presign_put(key, body.content_type, body.size_bytes)
    return UploadUrlOut(
        photo_key=up.key,
        upload_url=up.url,
        method=up.method,
        headers=up.headers,
        expires_in=up.expires_in,
    )


@router.put("/uploads/local/{key:path}", status_code=status.HTTP_204_NO_CONTENT, tags=["scans"])
async def local_upload(
    key: str,
    request: Request,
    storage: StorageDep,
    expires: Annotated[int, Query()],
    size: Annotated[int, Query()],
    sig: Annotated[str, Query(max_length=64)],
) -> None:
    """Development stand-in for R2: accepts a PUT only with a valid, unexpired signature
    for exactly this key, content type, and size. No login needed (like R2)."""
    if not isinstance(storage, LocalStorage):
        raise NotFound("Not found")
    content_type = request.headers.get("content-type", "")
    if (
        not PHOTO_KEY_RE.match(key)
        or size > settings.UPLOAD_MAX_BYTES
        or not storage.check_signature(key, expires, content_type, size, sig)
    ):
        raise Forbidden("Invalid or expired upload URL")

    # Read at most size+1 bytes, so a lying client can't make us buffer a huge body.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > size:
            raise BadRequest("Body is larger than signed size")
    if len(body) != size:
        raise BadRequest("Body size does not match")
    # File I/O is blocking: run it in the thread pool, not on the event loop.
    await run_in_threadpool(storage.save, key, bytes(body))


# ---------- scans ----------


@router.post("/scans", response_model=ScanOut, tags=["scans"])
def create_scan(
    body: ScanIn,
    response: Response,
    current: VerifiedMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
    backup: BackupReaderDep,
) -> ScanOut:
    """Read an uploaded list photo with the AI. Any staff member can scan.

    Answers with the scan: status "read" (lines to review) or "failed" (error_message,
    retryable). 201 when created; 200 with the existing scan for a repeated photo_key.
    429 with code "ai_budget_reached" when the store has used this month's AI budget.
    """
    scan, created = scan_service.start_scan(
        db, current.store_id, current.user.id, body.photo_key, body.type, storage, reader, backup
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return scan_service.scan_view(db, scan)


@router.get("/scans/{scan_id}", response_model=ScanOut, tags=["scans"])
def get_scan(scan_id: UUID, current: CurrentMemberDep, db: DbSession) -> ScanOut:
    return scan_service.scan_view(db, scan_service.get_scan(db, current.store_id, scan_id))


@router.post("/scans/{scan_id}/retry", response_model=ScanOut, tags=["scans"])
def retry_scan(
    scan_id: UUID,
    current: VerifiedMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
    backup: BackupReaderDep,
) -> ScanOut:
    """Read the photo again after a failed (or stuck) read."""
    scan = scan_service.retry_scan(db, current.store_id, scan_id, storage, reader, backup)
    return scan_service.scan_view(db, scan)


# ---------- transactions ----------


@router.post("/transactions", response_model=TransactionOut, tags=["transactions"])
def create_transaction(
    body: TransactionIn, response: Response, current: CurrentMemberDep, db: DbSession
) -> TransactionOut:
    """Save a stock-in or a sale. Any staff member can save; creating new products (stock
    in only) needs a manager or secretary. A sale that would take stock below 0 gets 409
    with code "negative_stock" and the product list, unless confirm is true.
    201 on the first save, 200 with the same body on a repeat."""
    result = stock_service.save_transaction_once(db, current, body)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return stock_service.transaction_view(db, result.transaction)


@router.get("/transactions", response_model=TransactionPage, tags=["transactions"])
def list_transactions(
    current: CurrentMemberDep,
    db: DbSession,
    type: Literal["stock_in", "sale", "adjustment"] | None = None,  # noqa: A002 - query param
    start: Annotated[date | None, Query(description="First day (Manila), YYYY-MM-DD")] = None,
    end: Annotated[date | None, Query(description="Last day (Manila), included")] = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
) -> TransactionPage:
    """This store's transactions, newest first, 20 per page. Optional Manila date range
    (voided ones are listed too, marked "voided")."""
    period = reports.make_range(start, end, default_today=False)
    rows, total = stock_service.list_transactions(db, current.store_id, type, page, period)
    return TransactionPage(
        items=rows,
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        pages=max(1, math.ceil(total / PAGE_SIZE)),
    )


@router.post(
    "/transactions/{transaction_id}/void", response_model=TransactionOut, tags=["transactions"]
)
def void_transaction(transaction_id: UUID, current: Writer, db: DbSession) -> TransactionOut:
    """Void a saved transaction (manager or secretary): nothing is deleted; stock is
    restored with reversing movements, and who/when is recorded. 409 if already voided."""
    txn = stock_service.void_transaction(db, current, transaction_id)
    return stock_service.transaction_view(db, txn)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut, tags=["transactions"])
def get_transaction(transaction_id: UUID, current: CurrentMemberDep, db: DbSession):
    txn = stock_service.get_transaction(db, current.store_id, transaction_id)
    return stock_service.transaction_view(db, txn)
