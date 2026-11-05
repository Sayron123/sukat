"""A product's selling price expressed in any unit it can be sold in."""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from app.products.units import ConvertibleProduct, UnitConversionError, convert

if TYPE_CHECKING:
    from app.products.models import Product


def price_per_unit(
    product: "Product | ConvertibleProduct", price_centavos: int | None, unit: str
) -> int | None:
    """The product's price (stored per BASE unit) for one `unit`, in whole centavos.

    Example: nails at ₱85.00/kg with 1 box = 25 kg -> 1 box = ₱2,125.00 (212500).
    Rounded half up to the centavo.

    @param price_centavos the product's price per base unit (None = not priced)
    @returns None when the product has no price, the unit is empty (never guessed), or
        the unit can't be converted
    """
    if price_centavos is None or not unit:
        return None
    try:
        base_qty = convert(product, Decimal(1), unit)
    except UnitConversionError:
        return None
    return int((base_qty * price_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def priced_line(
    product: "Product | ConvertibleProduct", price_centavos: int | None, qty: Decimal, unit: str
) -> tuple[int | None, int | None]:
    """(unit price, line total) in centavos when the price comes from the product.

    The total is the exact base quantity times the base-unit price, rounded once.
    Multiplying the already-rounded unit price would exaggerate rounding for small
    units: 500 g of ₱85.00/kg nails is ₱42.50, but 500 x round(8.5) centavos = ₱45.00.

    @returns (None, None) when the product has no price, the unit is empty, or the unit
        can't be converted
    """
    unit_price = price_per_unit(product, price_centavos, unit)
    if unit_price is None or price_centavos is None:
        return None, None
    base_qty = convert(product, qty, unit)
    total = int((base_qty * price_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return unit_price, total
