"""Data shapes for AI list reading.

Two layers:
- RawLine / RAW_RESULT_SCHEMA: what the model is asked to return (JSON schema enforced by
  the API, then validated again with Pydantic). Uses short product refs ("P12") instead
  of UUIDs: fewer tokens, and an invented ref can't silently point at a real product.
- ScanLine: the provider-independent result the rest of the app uses.
"""

from dataclasses import dataclass, field
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
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
    provider: str = "anthropic"  # which price list applies (app/ai/pricing.py)

    @property
    def tokens_in(self) -> int:
        return self.input_tokens + self.cache_write_tokens + self.cache_read_tokens


@dataclass(frozen=True)
class ReadResult:
    lines: list[ScanLine]
    usage: AIUsageInfo
    raw: dict = field(default_factory=dict)  # the model's JSON, stored on the scan


# ---------- multi-step scan: what each AI step returns ----------


class ReadLine(BaseModel):
    """Step 1 "read": one row exactly as written. No matching, no math."""

    raw_text: str
    qty_text: str | None
    unit_text: str | None
    price_text: str | None  # price for one unit, as written ("@850", "850/bx")
    total_text: str | None  # the line's amount, as written ("1,700"), for the math check
    confidence: float = Field(ge=0, le=1)


class ReadOutput(BaseModel):
    lines: list[ReadLine]


class MatchItem(BaseModel):
    """Step 2 "match": one line the code couldn't match, sent to the AI."""

    line: int  # index of the line in the read output
    text: str  # the item as written, e.g. "2 bx pakong 4 pulgada"


class MatchAnswer(BaseModel):
    line: int
    product_id: str | None  # an id from the product list (like "P12"), or null


class MatchOutput(BaseModel):
    matches: list[MatchAnswer]


def _nullable_string() -> dict:
    return {"anyOf": [{"type": "string"}, {"type": "null"}]}


def _object(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": required,
        "properties": properties,
    }


# JSON schemas sent to the provider (structured output). Each must list exactly its
# Pydantic model's fields; a test checks this.
READ_SCHEMA: dict = _object(
    {
        "lines": {
            "type": "array",
            "items": _object(
                {
                    "raw_text": {"type": "string"},
                    "qty_text": _nullable_string(),
                    "unit_text": _nullable_string(),
                    "price_text": _nullable_string(),
                    "total_text": _nullable_string(),
                    "confidence": {"type": "number"},
                },
                list(ReadLine.model_fields),
            ),
        }
    },
    ["lines"],
)

MATCH_SCHEMA: dict = _object(
    {
        "matches": {
            "type": "array",
            "items": _object(
                {"line": {"type": "integer"}, "product_id": _nullable_string()},
                list(MatchAnswer.model_fields),
            ),
        }
    },
    ["matches"],
)
