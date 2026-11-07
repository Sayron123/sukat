"""Step 3 "check": plain code, no AI.

Turns the text the read step copied into numbers (qty, price, written total), converts
the quantity with the product's units (the existing convert()), checks qty x price
against a written line total, and lists why a line needs a look:

- low_confidence: the read step wasn't sure (confidence < 0.8)
- no_product / new_product: no product matched
- no_qty / no_unit: not written or unreadable
- unknown_unit: the unit can't be converted for that product
- qty_too_small: rounds to 0 in the product's base unit
- total_mismatch: qty x price differs from the written line total

The same check_line() runs when the scan is read (stored for diagnosis) and every time
the review screen shows it (with the products as they are now).
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import TYPE_CHECKING

from app.core.config import settings
from app.products.units import ConvertibleProduct, UnitConversionError, convert

if TYPE_CHECKING:
    from app.products.models import Product

CONFIDENCE_THRESHOLD = 0.8
QTY_STEP = Decimal("0.001")  # NUMERIC(12,3)
MAX_QTY = Decimal("999999999")
MAX_CENTAVOS = 999_999_999

_FRACTION = re.compile(r"^(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)$")
_DECIMAL = re.compile(r"\d+(?:\.\d+)?")
_UNICODE_FRACTIONS = {"½": " 1/2", "¼": " 1/4", "¾": " 3/4", "⅓": " 1/3", "⅔": " 2/3"}
_MONEY = re.compile(r"\d[\d,]*(?:\.\d+)?")


def quantize_qty(value: Decimal) -> Decimal:
    return value.quantize(QTY_STEP, rounding=ROUND_HALF_UP)


def line_total(qty: Decimal | None, unit_price_centavos: int | None) -> int | None:
    if qty is None or unit_price_centavos is None:
        return None
    return int((qty * unit_price_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_qty(text: str | None) -> Decimal | None:
    """'10' -> 10, '2.5' -> 2.5, '1/2' -> 0.5, '1 1/2' and '1½' -> 1.5. None for
    unreadable, zero or negative."""
    if not text:
        return None
    t = text.strip().lower()
    for char, frac in _UNICODE_FRACTIONS.items():
        t = t.replace(char, frac)
    t = t.replace(",", "").strip()
    m = _FRACTION.match(t)
    try:
        if m:
            whole, num, den = m.groups()
            if int(den) == 0:
                return None
            value = Decimal(whole or 0) + Decimal(num) / Decimal(den)
        else:
            number = _DECIMAL.search(t)
            if number is None or number.start() != 0:
                return None  # "?5", "x2": unreadable start, don't guess
            value = Decimal(number.group())
    except InvalidOperation:
        return None
    if not value.is_finite() or value <= 0 or value > MAX_QTY:
        return None
    return value


def parse_money(text: str | None) -> int | None:
    """'@250' -> 25000, '₱1,250.50' -> 125050, 'P85/kg' -> 8500, '= 2,500' -> 250000
    (centavos). None when there's no number."""
    if not text:
        return None
    m = _MONEY.search(text)
    if m is None:
        return None
    try:
        value = Decimal(m.group().replace(",", ""))
    except InvalidOperation:
        return None
    centavos = int((value * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return centavos if 0 <= centavos <= MAX_CENTAVOS else None


def total_mismatch(
    qty: Decimal | None, unit_price_centavos: int | None, written_total_centavos: int | None
) -> bool:
    """True when a written line total doesn't equal qty x price (within
    SCAN_TOTAL_TOLERANCE_CENTAVOS, since totals are often rounded)."""
    computed = line_total(qty, unit_price_centavos)
    if computed is None or written_total_centavos is None:
        return False
    return abs(computed - written_total_centavos) > settings.SCAN_TOTAL_TOLERANCE_CENTAVOS


def check_line(
    *,
    confidence: float,
    product: "Product | ConvertibleProduct | None",
    is_new: bool,
    qty: Decimal | None,
    unit: str,
    unit_price_centavos: int | None,
    written_total_centavos: int | None,
) -> tuple[list[str], Decimal | None]:
    """Why the line needs a look (empty = looks fine), and its qty in the product's
    base unit (None when it can't be worked out)."""
    reasons: list[str] = []
    qty_base: Decimal | None = None
    if confidence < CONFIDENCE_THRESHOLD:
        reasons.append("low_confidence")
    if product is None:
        reasons.append("new_product" if is_new else "no_product")
    if qty is None:
        reasons.append("no_qty")
    if not unit:
        # Never guess the unit (1 box of nails is not 1 kg): staff must enter it.
        reasons.append("no_unit")
    if product is not None and qty is not None and unit:
        try:
            qty_base = quantize_qty(convert(product, qty, unit))
            if qty_base <= 0:
                reasons.append("qty_too_small")
                qty_base = None
        except UnitConversionError:
            reasons.append("unknown_unit")
    if total_mismatch(qty, unit_price_centavos, written_total_centavos):
        reasons.append("total_mismatch")
    return reasons, qty_base
