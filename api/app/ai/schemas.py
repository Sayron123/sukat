"""Data shapes for AI list reading.

- ReadLine / READ_SCHEMA and MatchAnswer / MATCH_SCHEMA: what each AI step returns (a
  JSON schema enforced by the provider, then validated again with Pydantic). Products
  are named by short refs ("P12"): fewer tokens, and an invented ref matches nothing.
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


class ScanLine(BaseModel):
    """One line read from the photo, mapped back to this store's products."""

    raw_text: str
    product_id: UUID | None
    suggested_new_name: str | None
    qty: Decimal | None  # None when the model's number was unusable (<= 0)
    unit: str
    unit_price_centavos: int | None
    confidence: float = Field(ge=0, le=1)
    # The line's amount as written (None if not written), for the qty x price check.
    line_total_centavos: int | None = None


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
    usage: AIUsageInfo  # all AI calls of this read, added up
    raw: dict = field(default_factory=dict)  # the model's JSON, stored on the scan
    # One (ai_usage feature, usage) per AI request; empty = one "scan_read" call.
    calls: list[tuple[str, AIUsageInfo]] = field(default_factory=list)
    # Each step's output (read, match, check), stored on the scan to find errors.
    steps: dict | None = None
    ai_requests: int = 1


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


class AIUsageOut(BaseModel):
    month: str
    resets_on: date
    budget_centavos: int
    spent_centavos: int
    remaining_centavos: int
    scans_centavos: int
    chat_centavos: int
    reached: bool
