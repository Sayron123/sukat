"""Scan API: send a list photo to the AI and get reviewable lines back."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.ai.anthropic_reader import get_vision_reader
from app.ai.base import VisionReader
from app.auth.deps import CurrentMember, CurrentMemberDep, DbSession
from app.core.errors import Conflict, NotFound
from app.inventory.models import Scan
from app.inventory.scan_service import is_stale_pending, review_lines, run_read
from app.inventory.uploads import StorageDep, key_belongs_to_store

router = APIRouter(tags=["scans"])

ReaderDep = Annotated[VisionReader, Depends(get_vision_reader)]


class ScanIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    photo_key: str
    type: Literal["sale", "stock_in"] = "stock_in"


class ReviewLineOut(BaseModel):
    raw_text: str
    product_id: UUID | None
    product_name: str | None
    base_unit: str | None
    suggested_new_name: str | None
    is_new: bool
    qty: Decimal | None
    unit: str
    qty_base: Decimal | None
    unit_price_centavos: int | None
    line_total_centavos: int | None
    confidence: float
    needs_check: bool
    check_reasons: list[str]


class ScanOut(BaseModel):
    id: UUID
    type: str
    status: str
    error_message: str | None
    retryable: bool
    model: str | None
    lines: list[ReviewLineOut]
    created_at: datetime


STALE_MESSAGE = "Reading stopped before it finished. Please try again."


def _out(db: DbSession, scan: Scan) -> ScanOut:
    if is_stale_pending(scan):
        # Shown as failed so the phone stops waiting and offers Retry.
        status_, error, retryable = "failed", STALE_MESSAGE, True
    else:
        status_, error = scan.status, scan.error_message
        retryable = scan.status == "failed" and bool((scan.ai_result_json or {}).get("retryable"))
    return ScanOut(
        id=scan.id,
        type=scan.type,
        status=status_,
        error_message=error,
        retryable=retryable,
        model=scan.model,
        lines=[ReviewLineOut(**line) for line in review_lines(db, scan)],
        created_at=scan.created_at,
    )


def _get_scan(db: DbSession, current: CurrentMember, scan_id: UUID) -> Scan:
    scan = db.scalar(select(Scan).where(Scan.id == scan_id, Scan.store_id == current.store_id))
    if scan is None:
        raise NotFound("Scan not found")
    return scan


@router.post("/scans", response_model=ScanOut)
def create_scan(
    body: ScanIn,
    response: Response,
    current: CurrentMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
) -> ScanOut:
    """Read an uploaded list photo with the AI. Any staff member can scan.

    Always answers with the scan: status "read" (lines to review) or "failed" (with
    error_message and retryable). Sending the same photo_key again returns the existing
    scan instead of paying for a second AI read (safe for the phone to retry).
    """
    if not key_belongs_to_store(body.photo_key, current.store_id):
        raise NotFound("Photo not found")

    existing = db.scalar(
        select(Scan).where(Scan.store_id == current.store_id, Scan.photo_key == body.photo_key)
    )
    if existing is not None:
        return _out(db, existing)

    scan = Scan(
        store_id=current.store_id,
        type=body.type,
        photo_key=body.photo_key,
        status="pending",
        created_by=current.user.id,
    )
    db.add(scan)
    try:
        db.commit()
    except IntegrityError:
        # The same photo was sent twice at the same moment; the other request reads it.
        db.rollback()
        existing = db.scalar(
            select(Scan).where(Scan.store_id == current.store_id, Scan.photo_key == body.photo_key)
        )
        if existing is None:
            raise
        return _out(db, existing)
    run_read(db, scan, storage, reader)
    db.refresh(scan)
    response.status_code = status.HTTP_201_CREATED
    return _out(db, scan)


@router.get("/scans/{scan_id}", response_model=ScanOut)
def get_scan(scan_id: UUID, current: CurrentMemberDep, db: DbSession) -> ScanOut:
    return _out(db, _get_scan(db, current, scan_id))


@router.post("/scans/{scan_id}/retry", response_model=ScanOut)
def retry_scan(
    scan_id: UUID,
    current: CurrentMemberDep,
    db: DbSession,
    storage: StorageDep,
    reader: ReaderDep,
) -> ScanOut:
    """Read the photo again after a failed (or stuck) read. A scan that was read
    successfully or saved is never re-read: its lines may already be under review or
    be the record of a saved delivery."""
    scan = _get_scan(db, current, scan_id)
    if scan.status == "saved":
        raise Conflict("This scan is already saved")
    if scan.status == "read":
        raise Conflict("This scan was already read")
    if scan.status == "pending" and not is_stale_pending(scan):
        raise Conflict("This scan is still being read")
    run_read(db, scan, storage, reader)
    db.refresh(scan)
    return _out(db, scan)
