"""Sale scans: existing products only, default prices, and 'price differs'."""

from decimal import Decimal

from app.products.pricing import price_per_unit
from tests.conftest import make_product, scan_line, upload_photo


def _nails(api, headers, price=8500):
    return make_product(
        api,
        headers,
        name='Common Wire Nail 4"',
        category="Nails & Screws",
        base_unit="kg",
        price_centavos=price,
        aliases=["pako 4"],
        conversions=[{"from_unit": "box", "factor": "25"}],
    )


def _scan(api, headers, storage, reader, lines, scan_type="sale"):
    reader.lines = lines
    key = upload_photo(api, headers, storage)
    res = api.post("/scans", json={"photo_key": key, "type": scan_type}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_sale_uses_product_price_when_receipt_has_none(api, manager, storage, reader):
    nails = _nails(api, manager)
    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [
            scan_line(nails["id"], raw_text="3 kg pako 4", qty=Decimal("3"), unit="kg"),
            scan_line(nails["id"], raw_text="2 bx pako 4", qty=Decimal("2"), unit="box"),
        ],
    )
    kg, box = scan["lines"]
    assert kg["unit_price_centavos"] == 8500 and kg["price_source"] == "product"
    assert kg["line_total_centavos"] == 25500
    # Price is per kg; one box is 25 kg.
    assert box["unit_price_centavos"] == 212500 and box["expected_unit_price_centavos"] == 212500
    assert box["warnings"] == [] and box["needs_check"] is False
    assert reader.calls[0]["type"] == "sale"


def test_written_price_that_differs_is_flagged(api, manager, storage, reader):
    nails = _nails(api, manager)
    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [
            scan_line(nails["id"], qty=Decimal("2"), unit="kg", unit_price_centavos=9000),
            scan_line(nails["id"], qty=Decimal("1"), unit="kg", unit_price_centavos=8500),
        ],
    )
    differs, same = scan["lines"]
    assert differs["unit_price_centavos"] == 9000 and differs["price_source"] == "receipt"
    assert (
        differs["warnings"] == ["price_differs"] and differs["expected_unit_price_centavos"] == 8500
    )
    assert differs["needs_check"] is False  # a warning, not a check
    assert same["warnings"] == []


def test_sale_never_suggests_new_products(api, db, manager, storage, reader):
    from sqlalchemy import select

    from app.inventory.models import Scan

    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [scan_line(None, raw_text="5 bakal 16", suggested_new_name="Deformed Bar 16mm x 6m")],
    )
    line = scan["lines"][0]
    assert line["is_new"] is False and line["suggested_new_name"] is None
    assert line["check_reasons"] == ["no_product"] and line["needs_check"] is True
    stored = db.scalar(select(Scan.ai_result_json))
    assert stored["lines"][0]["suggested_new_name"] is None  # removed before saving


def test_unpriced_product_leaves_price_empty(api, manager, storage, reader):
    nails = _nails(api, manager, price=None)
    line = _scan(api, manager, storage, reader, [scan_line(nails["id"], unit="kg")])["lines"][0]
    assert line["unit_price_centavos"] is None and line["price_source"] is None
    assert line["warnings"] == []


def test_stock_in_prices_are_not_defaulted_or_compared(api, manager, storage, reader):
    nails = _nails(api, manager)
    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [
            scan_line(nails["id"], unit="kg"),
            scan_line(nails["id"], unit="kg", unit_price_centavos=6000),  # supplier cost
        ],
        scan_type="stock_in",
    )
    no_price, cost = scan["lines"]
    assert (
        no_price["unit_price_centavos"] is None and no_price["expected_unit_price_centavos"] is None
    )
    assert cost["warnings"] == [] and cost["price_source"] == "receipt"


def test_price_per_unit():
    from dataclasses import dataclass, field

    @dataclass
    class C:
        from_unit: str
        factor: Decimal

    @dataclass
    class P:
        name: str = "Paint"
        base_unit: str = "gal"
        conversions: list = field(default_factory=lambda: [C("l", Decimal("0.25"))])

    assert price_per_unit(P(), 120000, "gal") == 120000
    assert price_per_unit(P(), 120000, "l") == 30000
    assert price_per_unit(P(), 120001, "l") == 30000  # 30000.25 rounds to 30000
    assert price_per_unit(P(), 120002, "l") == 30001  # 30000.5 rounds half up
    assert price_per_unit(P(), 120000, "kg") is None
    assert price_per_unit(P(), None, "gal") is None


def test_review_total_for_small_units_is_not_rounded_twice(api, manager, storage, reader):
    nails = _nails(api, manager)  # ₱85.00 per kg
    line = _scan(
        api, manager, storage, reader, [scan_line(nails["id"], qty=Decimal("500"), unit="g")]
    )["lines"][0]
    assert line["unit_price_centavos"] == 9  # 8.5 centavos per gram, shown rounded
    assert line["line_total_centavos"] == 4250  # but the total is exact: ₱42.50
