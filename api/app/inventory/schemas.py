from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.products.schemas import Category, Name, PriceCentavos, Unit


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
    type: Literal["stock_in"] = "stock_in"
    scan_id: UUID | None = None
    lines: list[TransactionLineIn] = Field(min_length=1, max_length=200)


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
