"""Scoring AI-read lines against expected lines. Pure functions, unit-tested."""

from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from app.ai.schemas import ScanLine
from app.products.units import normalize_unit


@dataclass(frozen=True)
class ExpectedLine:
    product_id: UUID | None  # None = the item is not in the catalog (a "new" product)
    qty: Decimal
    unit: str


@dataclass
class CaseScore:
    expected: int = 0
    predicted: int = 0
    product_ok: int = 0
    qty_ok: int = 0
    unit_ok: int = 0
    all_ok: int = 0
    missing: int = 0  # expected lines with no predicted line
    extra: int = 0  # predicted lines with no expected line
    notes: list[str] = field(default_factory=list)

    def add(self, other: "CaseScore") -> None:
        for name in (
            "expected",
            "predicted",
            "product_ok",
            "qty_ok",
            "unit_ok",
            "all_ok",
            "missing",
            "extra",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))


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
        s.all_ok += product and qty and unit
        if not (product and qty and unit):
            s.notes.append(
                f'"{got.raw_text}": got {got.qty} {got.unit}'
                f"{'' if product else ' (wrong product)'}; expected {exp.qty} {exp.unit}"
            )
    s.extra = len(predicted) - used
    return s


def pct(part: int, whole: int) -> str:
    return f"{100 * part / whole:5.1f}%" if whole else "    -"
