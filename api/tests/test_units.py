"""Unit conversion service. Pure functions: no database needed."""

from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from app.products.units import UnitConversionError, convert, normalize_unit


@dataclass
class Conv:
    from_unit: str
    factor: Decimal


@dataclass
class P:
    name: str
    base_unit: str
    conversions: list[Conv] = field(default_factory=list)


NAILS = P('Common Wire Nail 4"', "kg", [Conv("box", Decimal("25"))])
CEMENT = P("Portland Cement 40kg", "bag", [Conv("kg", Decimal("0.025"))])
PAINT = P("Latex Paint", "gal", [Conv("l", Decimal("0.25"))])
WIRE = P("THHN Wire #12", "m", [Conv("box", Decimal("150"))])


def D(s: str) -> Decimal:
    return Decimal(s)


# --- the three required cases ---


def test_nails_grams_to_kg():
    assert convert(NAILS, D("500"), "g") == D("0.5")
    assert convert(NAILS, D("250"), "grams") == D("0.25")


def test_nails_box_to_kg():
    assert convert(NAILS, D("2"), "box") == D("50")
    assert convert(NAILS, D("0.5"), "Kahon") == D("12.5")


def test_unknown_unit_raises_clear_error():
    with pytest.raises(UnitConversionError) as exc:
        convert(NAILS, D("3"), "bundle")
    msg = str(exc.value)
    assert '"bundle"' in msg and "kg" in msg and "box" in msg and "Common Wire Nail" in msg


# --- the other rules ---


def test_same_as_base_unit_returns_qty_unchanged():
    assert convert(CEMENT, D("3"), "bag") == D("3")
    assert convert(CEMENT, D("3"), " SAKO ") == D("3")  # synonym of bag


def test_product_conversion_beats_metric():
    assert convert(CEMENT, D("20"), "kg") == D("0.5")  # 20 kg = half a 40 kg bag


def test_metric_into_a_product_conversion():
    assert convert(CEMENT, D("10000"), "g") == D("0.25")  # g -> kg -> bag
    assert convert(PAINT, D("500"), "ml") == D("0.125")  # ml -> l -> gal


def test_metric_length():
    assert convert(WIRE, D("250"), "cm") == D("2.5")
    assert convert(WIRE, D("1"), "box") == D("150")


def test_different_kinds_do_not_mix():
    with pytest.raises(UnitConversionError):
        convert(WIRE, D("1"), "kg")  # mass cannot become length
    with pytest.raises(UnitConversionError):
        convert(P("Hollow Block", "pc"), D("1"), "kg")


def test_exact_decimal_math():
    total = sum(convert(NAILS, D("100"), "g") for _ in range(3))
    assert total == D("0.3")  # floats would give 0.30000000000000004


def test_bad_qty_is_rejected():
    for bad in (Decimal("NaN"), Decimal("Infinity")):
        with pytest.raises(ValueError):
            convert(NAILS, bad, "kg")
    with pytest.raises(ValueError):
        convert(NAILS, 1.5, "kg")  # type: ignore[arg-type]


def test_normalize_unit():
    assert normalize_unit(" Kilos ") == "kg"
    assert normalize_unit("pcs.") == "pc"
    assert normalize_unit("cu.m") == "cu.m"
    assert normalize_unit("Litro") == "l"
