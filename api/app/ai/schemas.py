"""Data shapes for AI list reading.

Two layers:
- RawLine / RAW_RESULT_SCHEMA: what the model is asked to return (JSON schema enforced by
  the API, then validated again with Pydantic). Uses short product refs ("P12") instead
  of UUIDs: fewer tokens, and an invented ref can't silently point at a real product.
- ScanLine: the provider-independent result the rest of the app uses.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class CatalogConversion:
    from_unit: str
    factor: Decimal


@dataclass(frozen=True)
class CatalogEntry:
    """One product as the AI sees it."""

    product_id: UUID
    name: str
    base_unit: str
    aliases: tuple[str, ...] = ()
    conversions: tuple[CatalogConversion, ...] = ()


class RawLine(BaseModel):
    raw_text: str
    product_ref: str | None
    suggested_new_name: str | None
    qty: Decimal
    unit: str
    unit_price: Decimal | None
    line_total: Decimal | None
    confidence: float


class RawResult(BaseModel):
    lines: list[RawLine]


def _nullable(json_type: str) -> dict:
    return {"anyOf": [{"type": json_type}, {"type": "null"}]}


# Must list exactly RawLine's fields (a test checks this).
RAW_RESULT_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["lines"],
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": list(RawLine.model_fields),
                "properties": {
                    "raw_text": {"type": "string"},
                    "product_ref": _nullable("string"),
                    "suggested_new_name": _nullable("string"),
                    "qty": {"type": "number"},
                    "unit": {"type": "string"},
                    "unit_price": _nullable("number"),
                    "line_total": _nullable("number"),
                    "confidence": {"type": "number"},
                },
            },
        }
    },
}


class ScanLine(BaseModel):
    """One line read from the photo, mapped back to this store's products."""

    raw_text: str
    product_id: UUID | None
    suggested_new_name: str | None
    qty: Decimal | None  # None when the model's number was unusable (<= 0)
    unit: str
    unit_price_centavos: int | None
    confidence: float = Field(ge=0, le=1)


@dataclass(frozen=True)
class AIUsageInfo:
    model: str  # the model that actually answered (a refusal fallback may differ)
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def tokens_in(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


@dataclass(frozen=True)
class ReadResult:
    lines: list[ScanLine]
    usage: AIUsageInfo
    raw: dict = field(default_factory=dict)  # the model's JSON, stored on the scan


class AIUsageOut(BaseModel):
    month: str
    resets_on: date
    budget_centavos: int
    spent_centavos: int
    remaining_centavos: int
    scans_centavos: int
    chat_centavos: int
    reached: bool
