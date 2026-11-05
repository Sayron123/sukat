"""Reading a list photo with the AI, and turning the result into reviewable lines."""

from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.base import ImageType, VisionReader
from app.ai.schemas import AIReadError, CatalogConversion, CatalogEntry, ScanLine
from app.ai.usage import log_usage
from app.core.config import settings
from app.core.storage import Storage
from app.inventory.models import Scan
from app.products.models import Product
from app.products.units import UnitConversionError, convert

CONFIDENCE_THRESHOLD = 0.8
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


def run_read(db: Session, scan: Scan, storage: Storage, reader: VisionReader) -> None:
    """Read scan's photo with the AI and save the outcome on the scan (status read/failed).

    Commits. The AI call happens outside any open DB transaction, so a slow model never
    holds database locks or a pooled connection.
    """
    try:
        image = storage.read(scan.photo_key, settings.UPLOAD_MAX_BYTES)
    except ValueError:
        image = None
    media_type = sniff_image_type(image) if image else None
    if image is None or media_type is None:
        _fail(db, scan, "Photo not found or not an image. Please upload it again.", None)
        return

    catalog = store_catalog(db, scan.store_id)
    db.commit()  # end the read transaction before the slow AI call

    try:
        result = reader.read_list(image, media_type, catalog, scan.type)
    except AIReadError as e:
        _fail(db, scan, str(e), e)
        return

    scan.status = "read"
    scan.error_message = None
    scan.model = result.usage.model
    # Store lines already mapped to product ids: the AI's short refs (P1, P2...) only
    # mean something for the product list at the moment of reading.
    scan.ai_result_json = {
        "lines": [line.model_dump(mode="json") for line in result.lines],
        "raw": result.raw,
    }
    log_usage(db, scan.store_id, "scan_read", result.usage)
    db.commit()


def _fail(db: Session, scan: Scan, message: str, error: AIReadError | None) -> None:
    scan.status = "failed"
    scan.error_message = message[:500]
    # Not retryable errors are remembered in the message only; the API exposes `retryable`.
    scan.ai_result_json = {"retryable": bool(error and error.retryable)}
    if error and error.usage:
        log_usage(db, scan.store_id, "scan_read", error.usage)
    db.commit()


def quantize_qty(value: Decimal) -> Decimal:
    return value.quantize(QTY_STEP, rounding=ROUND_HALF_UP)


def line_total(qty: Decimal | None, unit_price_centavos: int | None) -> int | None:
    if qty is None or unit_price_centavos is None:
        return None
    return int((qty * unit_price_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def review_line(line: ScanLine, products: dict[UUID, Product]) -> dict:
    """Add what the review screen needs: product details, qty in base unit, and why the
    line needs checking (empty list = looks fine)."""
    product = products.get(line.product_id) if line.product_id else None
    reasons: list[str] = []
    qty_base: Decimal | None = None

    if line.confidence < CONFIDENCE_THRESHOLD:
        reasons.append("low_confidence")
    if product is None:
        reasons.append("new_product" if line.suggested_new_name else "no_product")
    if line.qty is None:
        reasons.append("no_qty")
    if product is not None and line.qty is not None:
        try:
            qty_base = quantize_qty(convert(product, line.qty, line.unit or product.base_unit))
            if qty_base <= 0:
                reasons.append("qty_too_small")
                qty_base = None
        except UnitConversionError:
            reasons.append("unknown_unit")

    return {
        "raw_text": line.raw_text,
        "product_id": product.id if product else None,
        "product_name": product.name if product else None,
        "base_unit": product.base_unit if product else None,
        "suggested_new_name": None if product else line.suggested_new_name,
        "is_new": product is None and bool(line.suggested_new_name),
        "qty": line.qty,
        "unit": line.unit,
        "qty_base": qty_base,
        "unit_price_centavos": line.unit_price_centavos,
        "line_total_centavos": line_total(line.qty, line.unit_price_centavos),
        "confidence": line.confidence,
        "needs_check": bool(reasons),
        "check_reasons": reasons,
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
    return [review_line(line, products) for line in lines]
