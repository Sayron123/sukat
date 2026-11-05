"""Convert a quantity in any unit to a product's base unit.

Order of attempts (first match wins):
  1. The unit IS the base unit                     -> qty
  2. The product has a conversion for the unit    -> qty * factor        (box -> kg)
  3. Standard metric between unit and base unit   -> g/kg, ml/l, mm/cm/m (g -> kg)
  4. Metric into one of the product's conversion units, then that conversion
     (ml -> l -> gal for paint sold per gallon with "1 l = 0.25 gal")
Otherwise UnitConversionError with a message that can be shown to staff.

All math uses Decimal, so 0.1 + 0.2 is exactly 0.3 (floats would drift).
"""

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Protocol

# Common ways staff write units -> the one spelling we store.
_SYNONYMS: dict[str, str] = {
    **dict.fromkeys(("pc", "pcs", "piece", "pieces", "piraso", "pirasos"), "pc"),
    **dict.fromkeys(("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"), "kg"),
    **dict.fromkeys(("g", "gm", "gms", "gram", "grams", "gramo"), "g"),
    **dict.fromkeys(("m", "mtr", "mtrs", "meter", "meters", "metre", "metres"), "m"),
    **dict.fromkeys(("cm", "centimeter", "centimeters"), "cm"),
    **dict.fromkeys(("mm", "millimeter", "millimeters"), "mm"),
    **dict.fromkeys(("l", "ltr", "ltrs", "liter", "liters", "litre", "litres", "litro"), "l"),
    **dict.fromkeys(("ml", "cc", "milliliter", "milliliters"), "ml"),
    **dict.fromkeys(("gal", "gals", "gallon", "gallons", "galon"), "gal"),
    **dict.fromkeys(("ft", "foot", "feet"), "ft"),
    **dict.fromkeys(("bag", "bags", "sako"), "bag"),
    **dict.fromkeys(("box", "boxes", "bx", "bxs", "kahon"), "box"),
    **dict.fromkeys(("roll", "rolls", "rl", "rls", "rolyo"), "roll"),
    **dict.fromkeys(("sheet", "sheets", "sht", "shts"), "sheet"),
}

# Every unit spelling we recognise after normalizing (used to strip units from text).
KNOWN_UNITS: frozenset[str] = frozenset(
    {*_SYNONYMS.values(), "cu.m", "can", "set", "pair", "tube", "pack"}
)

# Metric units: (dimension, size in the dimension's reference unit).
_METRIC: dict[str, tuple[str, Decimal]] = {
    "g": ("mass", Decimal("0.001")),
    "kg": ("mass", Decimal("1")),
    "ml": ("volume", Decimal("0.001")),
    "l": ("volume", Decimal("1")),
    "mm": ("length", Decimal("0.001")),
    "cm": ("length", Decimal("0.01")),
    "m": ("length", Decimal("1")),
}


class UnitConversionError(ValueError):
    """The unit cannot be converted to the product's base unit."""


class _Conversion(Protocol):
    from_unit: str
    factor: Decimal


class ConvertibleProduct(Protocol):
    """Anything with these attributes works (the Product model, or a test stand-in)."""

    name: str
    base_unit: str
    conversions: Iterable[_Conversion]


def normalize_unit(unit: str) -> str:
    """Lowercase, trim, drop a trailing dot, and map synonyms: " Kilos." -> "kg".
    Unknown units are returned cleaned but otherwise unchanged ("cu.m" stays "cu.m")."""
    cleaned = re.sub(r"\s+", " ", unit).strip().lower().rstrip(".")
    return _SYNONYMS.get(cleaned, cleaned)


def _metric_ratio(from_unit: str, to_unit: str) -> Decimal | None:
    """How many to_unit are in one from_unit, if both are metric of the same kind."""
    a, b = _METRIC.get(from_unit), _METRIC.get(to_unit)
    if a is None or b is None or a[0] != b[0]:
        return None
    return a[1] / b[1]


def convert(product: ConvertibleProduct, qty: Decimal, unit: str) -> Decimal:
    """Return `qty` of `unit` expressed in the product's base unit.

    @param product  needs name, base_unit, and conversions (from_unit, factor)
    @param qty      a finite Decimal (may be negative, e.g. for returns)
    @param unit     what the user typed: "kg", "Kilos", "box", "sako", ...
    @returns        exact Decimal in base units. Not rounded: round when storing.
    @raises UnitConversionError if no path exists; ValueError for a non-finite qty
    """
    if not isinstance(qty, Decimal) or not qty.is_finite():
        raise ValueError("qty must be a finite Decimal")

    target = normalize_unit(unit)
    base = normalize_unit(product.base_unit)
    if target == base:
        return qty

    factors = {normalize_unit(c.from_unit): Decimal(c.factor) for c in product.conversions}
    if target in factors:
        return qty * factors[target]

    ratio = _metric_ratio(target, base)
    if ratio is not None:
        return qty * ratio

    for conv_unit, factor in factors.items():
        ratio = _metric_ratio(target, conv_unit)
        if ratio is not None:
            return qty * ratio * factor

    known = sorted({base, *factors})
    raise UnitConversionError(
        f'Cannot convert "{unit}" to {base} for {product.name}. '
        f"Known units: {', '.join(known)}. Add a unit conversion to the product."
    )


def is_unit_word(word: str) -> bool:
    """True for a word that is a unit: "bx", "Kilos", "pcs." ..."""
    return normalize_unit(word) in KNOWN_UNITS
