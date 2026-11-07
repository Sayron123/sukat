"""Reading a list photo with the AI, and turning the result into reviewable lines."""

import re
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.base import ImageType, VisionReader
from app.ai.errors import AIReadError
from app.ai.scan_check import (  # noqa: F401  (quantize_qty, line_total: used by stock_service)
    CONFIDENCE_THRESHOLD,
    check_line,
    line_total,
    quantize_qty,
)
from app.ai.schemas import CatalogConversion, CatalogEntry, ScanLine
from app.ai.usage import log_usage
from app.core.config import settings
from app.core.errors import Conflict, NotFound
from app.core.storage import Storage
from app.inventory.models import Scan
from app.inventory.schemas import ReviewLineOut, ScanOut
from app.products.models import Product
from app.products.pricing import price_per_unit, priced_line

STALE_MESSAGE = "Reading stopped before it finished. Please try again."

PHOTO_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
# "<store uuid>/scans/<32 hex>.<ext>": nothing else is ever a valid photo key.
PHOTO_KEY_RE = re.compile(r"^([0-9a-f-]{36})/scans/[0-9a-f]{32}\.(jpg|png|webp)$")


def new_photo_key(store_id: UUID, content_type: str) -> str:
    """A fresh storage key under the store's prefix (made by the server, never the client)."""
    return f"{store_id}/scans/{uuid.uuid4().hex}.{PHOTO_EXTENSIONS[content_type]}"


def key_belongs_to_store(key: str, store_id: UUID) -> bool:
    """True only for a well-formed photo key under this store's prefix."""
    m = PHOTO_KEY_RE.match(key)
    return bool(m) and m.group(1) == str(store_id)


QTY_STEP = Decimal("0.001")  # stock_qty has 3 decimals


def sniff_image_type(data: bytes) -> ImageType | None:
    """Real file type from the first bytes. The upload's Content-Type is only a claim."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def store_catalog(db: Session, store_id: UUID) -> list[CatalogEntry]:
    """This store's active products, as the AI should see them."""
    products = db.scalars(
        select(Product).where(Product.store_id == store_id, Product.archived.is_(False))
    ).all()
    return [
        CatalogEntry(
            product_id=p.id,
            name=p.name,
            base_unit=p.base_unit,
            aliases=tuple(a.alias for a in p.aliases),
            conversions=tuple(CatalogConversion(c.from_unit, c.factor) for c in p.conversions),
        )
        for p in products
    ]


# Statuses a read may overwrite. A scan that is "read" or "saved" is never changed by a
# late or repeated AI answer (e.g. after a save, its lines are the record of what arrived).
WRITABLE_STATUSES = ("pending", "failed")


def stale_after_seconds() -> float:
    """After this long, a "pending" scan can't still be reading (the AI client has given
    up by then), e.g. the server restarted mid-read."""
    return settings.AI_TIMEOUT_SECONDS * (settings.AI_MAX_RETRIES + 1) + 60


def is_stale_pending(scan: Scan) -> bool:
    if scan.status != "pending":
        return False
    age = (datetime.now(UTC) - scan.updated_at).total_seconds()
    return age > stale_after_seconds()


def run_read(db: Session, scan: Scan, storage: Storage, reader: VisionReader) -> None:
    """Read scan's photo with the AI and save the outcome on the scan (status read/failed).

    Assumes the caller checked the scan may be (re)read. Commits. The AI call happens
    outside any open DB transaction, so a slow model never holds locks or a pooled
    connection. The result is written only if the scan is still pending/failed.
    """
    scan.status = "pending"
    scan.error_message = None
    db.commit()  # marks the start (updated_at) for stale detection

    try:
        image = storage.read(scan.photo_key, settings.UPLOAD_MAX_BYTES)
    except ValueError:
        image = None
    media_type = sniff_image_type(image) if image else None
    if image is None or media_type is None:
        _finish_failed(db, scan, "Photo not found or not an image. Please upload it again.", None)
        return

    catalog = store_catalog(db, scan.store_id)
    db.commit()  # end the read transaction before the slow AI call

    try:
        result = reader.read_list(image, media_type, catalog, scan.type)
    except AIReadError as e:
        _finish_failed(db, scan, str(e), e)
        return

    # Tokens were spent either way: one ai_usage row per AI request (read, match).
    for feature, usage in result.calls or [("scan_read", result.usage)]:
        log_usage(db, scan.store_id, feature, usage)
    if _lock_if_writable(db, scan):
        scan.status = "read"
        scan.error_message = None
        scan.model = result.usage.model
        # Store lines already mapped to product ids: the AI's short refs (P1, P2...) only
        # mean something for the product list at the moment of reading.
        lines = result.lines
        if scan.type == "sale":
            # A sale can only be of existing products, whatever the AI suggested.
            lines = [line.model_copy(update={"suggested_new_name": None}) for line in lines]
        stored: dict = {
            "lines": [line.model_dump(mode="json") for line in lines],
            "raw": result.raw,
        }
        if result.steps is not None:
            # Each step's output (read, match, check), to see where errors happen.
            stored["steps"] = result.steps
            stored["ai_requests"] = result.ai_requests
        scan.ai_result_json = stored
    db.commit()


def _lock_if_writable(db: Session, scan: Scan) -> bool:
    """Lock the scan row and reload it; True if a read result may still be written.
    (Something else may have changed it during the AI call.)"""
    db.scalar(
        select(Scan)
        .where(Scan.id == scan.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return scan.status in WRITABLE_STATUSES


def _finish_failed(db: Session, scan: Scan, message: str, error: AIReadError | None) -> None:
    if error and error.usage:
        log_usage(db, scan.store_id, "scan_read", error.usage)
    if _lock_if_writable(db, scan):
        scan.status = "failed"
        scan.error_message = message[:500]
        scan.ai_result_json = {"retryable": bool(error and error.retryable)}
    db.commit()


def review_line(line: ScanLine, products: dict[UUID, Product], scan_type: str) -> dict:
    """Add what the review screen needs: product details, qty in base unit, the price to
    use, why the line needs checking (`check_reasons`), and softer `warnings`.

    For a sale: no new products; a missing price defaults to the product's price for
    that unit; a written price that differs from it gets the "price_differs" warning.
    For stock in, prices are supplier costs and are never compared or defaulted.
    """
    product = products.get(line.product_id) if line.product_id else None
    is_sale = scan_type == "sale"
    suggested = None if (product or is_sale) else line.suggested_new_name
    warnings: list[str] = []
    # Same rules as the scan's check step (app/ai/scan_check.py), with today's products.
    reasons, qty_base = check_line(
        confidence=line.confidence,
        product=product,
        is_new=bool(suggested),
        qty=line.qty,
        unit=line.unit,
        unit_price_centavos=line.unit_price_centavos,
        written_total_centavos=line.line_total_centavos,
    )

    unit_price = line.unit_price_centavos
    price_source = "receipt" if unit_price is not None else None
    total = line_total(line.qty, unit_price)
    expected = None
    if is_sale and product is not None:
        expected = price_per_unit(product, product.price_centavos, line.unit)
        if unit_price is None and expected is not None and line.qty is not None:
            # Same rule as saving, so the review total matches what gets saved.
            unit_price, total = priced_line(product, product.price_centavos, line.qty, line.unit)
            price_source = "product"
        elif unit_price is not None and expected is not None and unit_price != expected:
            warnings.append("price_differs")

    return {
        "raw_text": line.raw_text,
        "product_id": product.id if product else None,
        "product_name": product.name if product else None,
        "base_unit": product.base_unit if product else None,
        "suggested_new_name": suggested,
        "is_new": bool(suggested),
        "qty": line.qty,
        "unit": line.unit,
        "qty_base": qty_base,
        "unit_price_centavos": unit_price,
        "price_source": price_source,
        "expected_unit_price_centavos": expected,
        "line_total_centavos": total,
        "confidence": line.confidence,
        "needs_check": bool(reasons),
        "check_reasons": reasons,
        "warnings": warnings,
    }


def review_lines(db: Session, scan: Scan) -> list[dict]:
    """The scan's lines with current product data. Products archived or from another
    store since reading are treated as unmatched."""
    if scan.status not in ("read", "saved") or not scan.ai_result_json:
        return []
    lines = [ScanLine.model_validate(x) for x in scan.ai_result_json.get("lines", [])]
    ids = {line.product_id for line in lines if line.product_id}
    products = (
        {
            p.id: p
            for p in db.scalars(
                select(Product).where(
                    Product.store_id == scan.store_id,
                    Product.id.in_(ids),
                    Product.archived.is_(False),
                )
            )
        }
        if ids
        else {}
    )
    return [review_line(line, products, scan.type) for line in lines]


# ---------- scan lifecycle (used by the router) ----------


def get_scan(db: Session, store_id: UUID, scan_id: UUID) -> Scan:
    """@raises NotFound also for another store's scan"""
    scan = db.scalar(select(Scan).where(Scan.id == scan_id, Scan.store_id == store_id))
    if scan is None:
        raise NotFound("Scan not found")
    return scan


def start_scan(
    db: Session,
    store_id: UUID,
    user_id: UUID,
    photo_key: str,
    scan_type: str,
    storage: Storage,
    reader: VisionReader,
) -> tuple[Scan, bool]:
    """Create a scan for an uploaded photo and read it. Returns (scan, created).

    Sending the same photo_key again returns the existing scan (created=False) instead
    of paying for a second AI read, so the phone can safely retry.

    @raises NotFound if the key isn't a photo key of this store
    """
    if not key_belongs_to_store(photo_key, store_id):
        raise NotFound("Photo not found")

    def existing() -> Scan | None:
        return db.scalar(select(Scan).where(Scan.store_id == store_id, Scan.photo_key == photo_key))

    found = existing()
    if found is not None:
        return found, False

    scan = Scan(
        store_id=store_id, type=scan_type, photo_key=photo_key, status="pending", created_by=user_id
    )
    db.add(scan)
    try:
        db.commit()
    except IntegrityError:
        # The same photo was sent twice at the same moment; the other request reads it.
        db.rollback()
        found = existing()
        if found is None:
            raise
        return found, False
    run_read(db, scan, storage, reader)
    db.refresh(scan)
    return scan, True


def retry_scan(
    db: Session, store_id: UUID, scan_id: UUID, storage: Storage, reader: VisionReader
) -> Scan:
    """Read the photo again after a failed (or stuck) read. A scan that was read
    successfully or saved is never re-read: its lines may be under review or be the
    record of a saved delivery.

    @raises NotFound, Conflict (saved / already read / still reading)
    """
    scan = get_scan(db, store_id, scan_id)
    if scan.status == "saved":
        raise Conflict("This scan is already saved")
    if scan.status == "read":
        raise Conflict("This scan was already read")
    if scan.status == "pending" and not is_stale_pending(scan):
        raise Conflict("This scan is still being read")
    run_read(db, scan, storage, reader)
    db.refresh(scan)
    return scan


def scan_view(db: Session, scan: Scan) -> ScanOut:
    """The scan as the phone sees it. A stuck "pending" read is shown as a retryable
    failure so the phone stops waiting."""
    if is_stale_pending(scan):
        status, error, retryable = "failed", STALE_MESSAGE, True
    else:
        status, error = scan.status, scan.error_message
        retryable = scan.status == "failed" and bool((scan.ai_result_json or {}).get("retryable"))
    return ScanOut(
        id=scan.id,
        type=scan.type,
        status=status,
        error_message=error,
        retryable=retryable,
        model=scan.model,
        lines=[ReviewLineOut(**line) for line in review_lines(db, scan)],
        created_at=scan.created_at,
    )
