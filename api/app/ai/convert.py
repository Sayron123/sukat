"""Turning the model's raw JSON into ScanLines, and the catalog into prompt text.

Kept separate from the provider client so it is easy to unit-test.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from pydantic import ValidationError

from app.ai.schemas import CatalogEntry, RawLine, RawResult, ScanLine
from app.products.units import normalize_unit

MAX_PRICE_CENTAVOS = 999_999_999


def catalog_refs(catalog: list[CatalogEntry]) -> list[tuple[str, CatalogEntry]]:
    """Give each product a short ref (P1, P2, ...) in a stable order (name, then id),
    so the prompt text is byte-identical between scans and the prompt cache hits."""
    ordered = sorted(catalog, key=lambda e: (e.name.lower(), str(e.product_id)))
    return [(f"P{i}", entry) for i, entry in enumerate(ordered, start=1)]


def catalog_text(refs: list[tuple[str, CatalogEntry]]) -> str:
    """One product per line: `P12 | name | unit: kg | also: a, b | 1 box = 25 kg`."""
    if not refs:
        return "The store has no products yet. Use product_ref null for every line."
    rows = ["The store's products (ref | name | base unit | other names | other units):"]
    for ref, e in refs:
        parts = [ref, e.name, f"unit: {e.base_unit}"]
        if e.aliases:
            parts.append("also: " + ", ".join(e.aliases))
        if e.conversions:
            parts.append(
                "; ".join(
                    f"1 {c.from_unit} = {c.factor.normalize():f} {e.base_unit}"
                    for c in e.conversions
                )
            )
        rows.append(" | ".join(parts))
    return "\n".join(rows)


def _to_centavos(pesos: Decimal | None) -> int | None:
    if pesos is None or not pesos.is_finite() or pesos < 0:
        return None
    try:
        value = int((pesos * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except InvalidOperation:
        return None
    return value if value <= MAX_PRICE_CENTAVOS else None


def to_scan_line(raw: RawLine, refs: dict[str, CatalogEntry]) -> ScanLine:
    """Map one raw line to a ScanLine. Never raises: odd values become None / low
    confidence so the line is flagged for checking instead of breaking the scan."""
    entry = refs.get((raw.product_ref or "").strip().upper())
    qty = raw.qty if raw.qty.is_finite() and raw.qty > 0 else None
    unit = normalize_unit(raw.unit) or (entry.base_unit if entry else "")

    price = _to_centavos(raw.unit_price)
    if price is None and qty and raw.line_total is not None:
        # Only a line total was written: derive the unit price from it.
        price = _to_centavos(raw.line_total / qty)

    name = (raw.suggested_new_name or "").strip()[:160] or None
    return ScanLine(
        raw_text=raw.raw_text.strip()[:300],
        product_id=entry.product_id if entry else None,
        suggested_new_name=None if entry else name,
        qty=qty,
        unit=unit[:20],
        unit_price_centavos=price,
        confidence=min(max(float(raw.confidence), 0.0), 1.0),
    )


def parse_result(data: dict, refs: list[tuple[str, CatalogEntry]]) -> list[ScanLine]:
    """Validate the model's JSON and map it.

    @raises ValidationError if the overall shape is wrong
    """
    result = RawResult.model_validate(data)
    by_ref = dict(refs)
    return [to_scan_line(line, by_ref) for line in result.lines]


__all__ = ["ValidationError", "catalog_refs", "catalog_text", "parse_result", "to_scan_line"]
