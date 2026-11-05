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
    @returns None when the product has no price or the unit can't be converted
    """
    if price_centavos is None:
        return None
    try:
        base_qty = convert(product, Decimal(1), unit or product.base_unit)
    except UnitConversionError:
        return None
    return int((base_qty * price_centavos).quantize(Decimal(1), rounding=ROUND_HALF_UP))
