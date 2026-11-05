from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.constants import Category
from app.products.schemas import Name, PriceCentavos, Unit


class NewProductIn(BaseModel):
    """A product to create while saving (a line the AI marked "new")."""

    model_config = ConfigDict(extra="forbid")

    name: Name
    category: Category = "Others"
    base_unit: Unit


class TransactionLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Exactly one of these two.
    product_id: UUID | None = None
    new_product: NewProductIn | None = None
    qty: Decimal = Field(gt=0, max_digits=12, decimal_places=3)
    unit: Unit
    # Price per `unit` as written (supplier cost). Optional.
    unit_price_centavos: PriceCentavos | None = None
    # Index of the scan line this came from. The server reads raw_text and the AI's
    # suggestion from the stored scan (not from the client) for alias learning.
    scan_line: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _one_product(self) -> "TransactionLineIn":
        if (self.product_id is None) == (self.new_product is None):
            raise ValueError("give either product_id or new_product")
        return self


class TransactionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Made on the phone when the review screen opens (a UUID). Sending the same id again
    # never saves twice.
    client_request_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    type: Literal["stock_in", "sale"] = "stock_in"
    scan_id: UUID | None = None
    lines: list[TransactionLineIn] = Field(min_length=1, max_length=200)
    # Sales only: save even if some stock would go below 0 (stores sometimes sell before
    # recording the delivery). Without it, such a sale is refused with the list.
    confirm: bool = False

    @model_validator(mode="after")
    def _sale_rules(self) -> "TransactionIn":
        if self.type == "sale" and any(line.new_product for line in self.lines):
            raise ValueError("a sale can only include existing products")
        return self


class TransactionItemOut(BaseModel):
    line_no: int
    product_id: UUID
    product_name: str
    base_unit: str
    qty: Decimal
    unit: str
    qty_base: Decimal
    unit_price_centavos: int | None
    line_total_centavos: int | None
    stock_after: Decimal


class TransactionOut(BaseModel):
    id: UUID
    type: str
    status: str
    client_request_id: str
    scan_id: UUID | None
    total_centavos: int
    items: list[TransactionItemOut]
    created_at: datetime


# ---------- photo upload ----------


class UploadUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    size_bytes: int = Field(gt=0)


class UploadUrlOut(BaseModel):
    photo_key: str
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int


# ---------- scans ----------


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
    # "receipt" = written on the photo, "product" = filled in from the product's price.
    price_source: Literal["receipt", "product"] | None
    # Sales only: the product's price for this unit, to compare with a written price.
    expected_unit_price_centavos: int | None
    line_total_centavos: int | None
    confidence: float
    needs_check: bool
    check_reasons: list[str]  # must be looked at (amber "Check")
    warnings: list[str]  # worth a look, e.g. "price_differs"


class ScanOut(BaseModel):
    id: UUID
    type: str
    status: str
    error_message: str | None
    retryable: bool
    model: str | None
    lines: list[ReviewLineOut]
    created_at: datetime
