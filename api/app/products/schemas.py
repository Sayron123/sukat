import re
from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from app.products.constants import MAX_BULK_DELETE, Category
from app.products.units import normalize_unit


def _clean(value: str) -> str:
    """Trim, lowercase, and collapse inner spaces: "  Bakal   10MM " -> "bakal 10mm"."""
    return re.sub(r"\s+", " ", value).strip().lower()


def _not_blank(value: str) -> str:
    if not value:
        raise ValueError("must not be blank")
    return value


Name = Annotated[
    str, Field(max_length=160), AfterValidator(lambda v: _not_blank(re.sub(r"\s+", " ", v).strip()))
]
# Units are stored in one spelling ("Kilos" -> "kg") so conversions always match.
Unit = Annotated[str, Field(max_length=20), AfterValidator(lambda v: _not_blank(normalize_unit(v)))]
Alias = Annotated[str, Field(max_length=80), AfterValidator(lambda v: _not_blank(_clean(v)))]
# Max ₱9,999,999.99 per unit; fits the int4 column (2,147,483,647) with room to spare.
PriceCentavos = Annotated[int, Field(ge=0, le=999_999_999)]
Qty = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3)]
Factor = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]


class ConversionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_unit: Unit
    factor: Factor  # 1 from_unit = factor base_unit


def _check_lists(aliases: list[str] | None, conversions: list[ConversionIn] | None) -> None:
    if aliases is not None and len(set(aliases)) != len(aliases):
        raise ValueError("aliases must not repeat")
    if conversions is not None:
        units = [c.from_unit for c in conversions]
        if len(set(units)) != len(units):
            raise ValueError("each conversion unit may appear only once")


class ProductCreate(BaseModel):
    # extra="forbid": sending stock_qty (or any unknown field) is a 422, not silently ignored.
    model_config = ConfigDict(extra="forbid")

    name: Name
    category: Category
    base_unit: Unit
    price_centavos: PriceCentavos | None = None
    low_stock_level: Qty | None = None
    aliases: list[Alias] = Field(default_factory=list, max_length=20)
    conversions: list[ConversionIn] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def _validate(self) -> "ProductCreate":
        _check_lists(self.aliases, self.conversions)
        if any(c.from_unit == self.base_unit for c in self.conversions):
            raise ValueError("a conversion cannot use the base unit itself")
        return self


class ProductUpdate(BaseModel):
    """Partial update. Omitted fields stay as they are. stock_qty is not accepted."""

    model_config = ConfigDict(extra="forbid")

    name: Name | None = None
    category: Category | None = None
    base_unit: Unit | None = None
    price_centavos: PriceCentavos | None = None
    low_stock_level: Qty | None = None
    # When given, these REPLACE the whole list.
    aliases: list[Alias] | None = Field(default=None, max_length=20)
    conversions: list[ConversionIn] | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _validate(self) -> "ProductUpdate":
        _check_lists(self.aliases, self.conversions)
        for field in ("name", "category", "base_unit"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ConversionOut(BaseModel):
    from_unit: str
    factor: Decimal


class ProductOut(BaseModel):
    id: UUID
    name: str
    category: str
    base_unit: str
    price_centavos: int | None
    stock_qty: Decimal
    low_stock_level: Decimal | None
    is_low_stock: bool
    archived: bool
    aliases: list[str]
    conversions: list[ConversionOut]
    created_at: datetime
    updated_at: datetime


class ProductPage(BaseModel):
    items: list[ProductOut]
    total: int
    page: int
    page_size: int
    pages: int


class CatalogItemOut(BaseModel):
    key: str
    name: str
    category: str
    base_unit: str
    aliases: list[str]
    conversions: list[ConversionOut]
    already_in_store: bool


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keys: list[str] = Field(min_length=1, max_length=500)


class ProductDeleteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[UUID] = Field(min_length=1, max_length=MAX_BULK_DELETE)


class ProductDeleteOut(BaseModel):
    deleted: int
    kept: list[str]


class SkippedItem(BaseModel):
    key: str
    name: str
    reason: str


class DroppedAlias(BaseModel):
    key: str
    alias: str
    reason: str


class ImportOut(BaseModel):
    created: int
    skipped: list[SkippedItem]
    dropped_aliases: list[DroppedAlias]
