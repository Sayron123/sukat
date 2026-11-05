"""Inventory HTTP endpoints: photo upload, scans, and transactions.

Thin: check access, call scan_service / stock_service, shape the response.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool

from app.ai.anthropic_reader import get_vision_reader
from app.ai.base import VisionReader
from app.auth.deps import CurrentMemberDep, DbSession
from app.core.config import settings
from app.core.errors import AppError, BadRequest, Forbidden, NotFound
from app.core.storage import LocalStorage, Storage, get_storage
from app.inventory import scan_service, stock_service
from app.inventory.scan_service import PHOTO_KEY_RE
from app.inventory.schemas import (
    ScanIn,
    ScanOut,
    TransactionIn,
    TransactionOut,
    UploadUrlIn,
    UploadUrlOut,
)

router = APIRouter()

StorageDep = Annotated[Storage, Depends(get_storage)]
ReaderDep = Annotated[VisionReader, Depends(get_vision_reader)]


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
    current: CurrentMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
) -> ScanOut:
    """Read an uploaded list photo with the AI. Any staff member can scan.

    Answers with the scan: status "read" (lines to review) or "failed" (error_message,
    retryable). 201 when created; 200 with the existing scan for a repeated photo_key.
    """
    scan, created = scan_service.start_scan(
        db, current.store_id, current.user.id, body.photo_key, body.type, storage, reader
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return scan_service.scan_view(db, scan)


@router.get("/scans/{scan_id}", response_model=ScanOut, tags=["scans"])
def get_scan(scan_id: UUID, current: CurrentMemberDep, db: DbSession) -> ScanOut:
    return scan_service.scan_view(db, scan_service.get_scan(db, current.store_id, scan_id))


@router.post("/scans/{scan_id}/retry", response_model=ScanOut, tags=["scans"])
def retry_scan(
    scan_id: UUID,
    current: CurrentMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
) -> ScanOut:
    """Read the photo again after a failed (or stuck) read."""
    scan = scan_service.retry_scan(db, current.store_id, scan_id, storage, reader)
    return scan_service.scan_view(db, scan)


# ---------- transactions ----------


@router.post("/transactions", response_model=TransactionOut, tags=["transactions"])
def create_transaction(
    body: TransactionIn, response: Response, current: CurrentMemberDep, db: DbSession
) -> TransactionOut:
    """Save a stock-in. Any staff member can save; creating new products needs a
    manager or secretary. 201 on the first save, 200 with the same body on a repeat."""
    result = stock_service.save_stock_in_once(db, current, body)
    response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
    return stock_service.transaction_view(db, result.transaction)


@router.get("/transactions/{transaction_id}", response_model=TransactionOut, tags=["transactions"])
def get_transaction(transaction_id: UUID, current: CurrentMemberDep, db: DbSession):
    txn = stock_service.get_transaction(db, current.store_id, transaction_id)
    return stock_service.transaction_view(db, txn)
