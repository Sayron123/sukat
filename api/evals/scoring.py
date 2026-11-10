"""Scoring AI-read lines against expected lines. Pure functions, unit-tested."""

from dataclasses import dataclass, field, fields
from decimal import Decimal
from uuid import UUID

from app.ai.schemas import ScanLine
from app.products.units import normalize_unit

# Sentinel: the expected file says nothing about price, so price isn't scored.
NOT_SCORED = object()


@dataclass(frozen=True)
class ExpectedLine:
    product_id: UUID | None  # None = the item is not in the catalog / store
    qty: Decimal
    unit: str
    # Price per unit as WRITTEN on the photo, in centavos: an int, None ("no price
    # written", so the AI must return none), or NOT_SCORED.
    unit_price_centavos: object = NOT_SCORED


@dataclass
class CaseScore:
    expected: int = 0
    predicted: int = 0
    product_ok: int = 0  # step 2 "match": right product
    qty_ok: int = 0
    unit_ok: int = 0
    read_ok: int = 0  # step 1 "read": qty and unit both right (they come only from the read)
    all_ok: int = 0  # final: product, qty and unit all right
    price_checked: int = 0  # paired lines whose expected price is given
    price_ok: int = 0
    missing: int = 0  # expected lines with no predicted line
    extra: int = 0  # predicted lines with no expected line
    # From the scan's stored steps (filled by the runner, not by score_case):
    scans: int = 0
    ai_requests: int = 0
    one_request_scans: int = 0  # every line matched by code: only the read call
    matched_by_code: int = 0
    matched_by_ai: int = 0
    not_matched: int = 0
    notes: list[str] = field(default_factory=list)

    def add(self, other: "CaseScore") -> None:
        for f in fields(self):
            if f.name != "notes":
                setattr(self, f.name, getattr(self, f.name) + getattr(other, f.name))


def pair_lines(
    expected: list[ExpectedLine], predicted: list[ScanLine]
) -> list[tuple[ExpectedLine, ScanLine | None]]:
    """Pair each expected line with at most one predicted line.

    First by same product (in order), then the rest by position. So one skipped or
    extra line doesn't make every following line count as wrong.
    """
    remaining = list(range(len(predicted)))
    pairs: dict[int, int] = {}
    for ei, exp in enumerate(expected):
        if exp.product_id is None:
            continue
        for pi in remaining:
            if predicted[pi].product_id == exp.product_id:
                pairs[ei] = pi
                remaining.remove(pi)
                break
    for ei in range(len(expected)):
        if ei not in pairs and remaining:
            pairs[ei] = remaining.pop(0)
    return [(exp, predicted[pairs[i]] if i in pairs else None) for i, exp in enumerate(expected)]


def score_case(expected: list[ExpectedLine], predicted: list[ScanLine]) -> CaseScore:
    """Product / qty / unit for every expected line; price only where the expected
    file gives one. Prices are compared as read from the photo (before any default)."""
    s = CaseScore(expected=len(expected), predicted=len(predicted))
    used = 0
    for exp, got in pair_lines(expected, predicted):
        if got is None:
            s.missing += 1
            s.notes.append(f"missing: {exp.qty} {exp.unit}")
            continue
        used += 1
        product = got.product_id == exp.product_id
        qty = got.qty is not None and got.qty == exp.qty
        unit = normalize_unit(got.unit) == normalize_unit(exp.unit)
        s.product_ok += product
        s.qty_ok += qty
        s.unit_ok += unit
        s.read_ok += qty and unit
        s.all_ok += product and qty and unit
        problems = []
        if not product:
            problems.append("wrong product")
        if exp.unit_price_centavos is not NOT_SCORED:
            s.price_checked += 1
            if got.unit_price_centavos == exp.unit_price_centavos:
                s.price_ok += 1
            else:
                problems.append(f"price {got.unit_price_centavos} != {exp.unit_price_centavos}")
        if problems or not (qty and unit):
            s.notes.append(
                f'"{got.raw_text}": got {got.qty} {got.unit}; expected {exp.qty} {exp.unit}'
                + (f" ({', '.join(problems)})" if problems else "")
            )
    s.extra = len(predicted) - used
    return s


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "    -"
