from decimal import Decimal

from sqlalchemy import select

from app.ai.models import AIUsage
from app.ai.schemas import AIReadError, AIUsageInfo
from app.inventory.models import Scan
from tests.conftest import auth_header, make_product, scan_line, upload_photo


def _products(api, headers):
    nails = make_product(
        api,
        headers,
        name='Common Wire Nail 4"',
        category="Nails & Screws",
        base_unit="kg",
        aliases=["pako 4"],
        conversions=[{"from_unit": "box", "factor": "25"}],
    )
    cement = make_product(api, headers, aliases=["sem"])
    return nails, cement


def _member(api, manager):
    invite = api.post(
        "/staff/invites", json={"email": "member@example.com", "role": "member"}, headers=manager
    ).json()
    token = api.post(
        "/invites/accept",
        json={"token": invite["token"], "password": "member-pass-1", "full_name": "M"},
    ).json()["access_token"]
    return auth_header(token)


def test_member_can_scan_and_lines_are_converted_and_flagged(api, manager, storage, reader, db):
    nails, cement = _products(api, manager)
    reader.lines = [
        scan_line(
            nails["id"],
            raw_text="2 bx pako 4",
            qty=Decimal("2"),
            unit="box",
            unit_price_centavos=212500,
        ),
        scan_line(nails["id"], raw_text="500g pako 4", qty=Decimal("500"), unit="g"),
        scan_line(cement["id"], raw_text="10 sem", qty=Decimal("10"), unit="bag", confidence=0.6),
        scan_line(cement["id"], raw_text="3 drums sem", qty=Decimal("3"), unit="drum"),
        scan_line(None, raw_text="5 bakal 16", suggested_new_name="Deformed Bar 16mm x 6m"),
        scan_line(None, raw_text="??", qty=None),
    ]
    member = _member(api, manager)
    key = upload_photo(api, member, storage)
    res = api.post("/scans", json={"photo_key": key, "type": "stock_in"}, headers=member)
    assert res.status_code == 201, res.text
    scan = res.json()
    assert scan["status"] == "read" and scan["model"] == "fake-model"

    boxes, grams, low, drum, new, blank = scan["lines"]
    assert boxes["qty_base"] == "50.000" and boxes["needs_check"] is False
    assert boxes["line_total_centavos"] == 425000 and boxes["product_name"] == 'Common Wire Nail 4"'
    assert grams["qty_base"] == "0.500" and grams["base_unit"] == "kg"
    assert low["check_reasons"] == ["low_confidence"]
    assert drum["check_reasons"] == ["unknown_unit"] and drum["qty_base"] is None
    assert new["is_new"] is True and new["check_reasons"] == ["new_product"]
    assert set(blank["check_reasons"]) == {"no_product", "no_qty"}

    # The AI got this store's products and the right photo.
    call = reader.calls[0]
    assert {e.name for e in call["catalog"]} == {'Common Wire Nail 4"', "Portland Cement 40kg"}
    assert call["media_type"] == "image/jpeg" and call["type"] == "stock_in"

    usage = db.scalar(select(AIUsage))
    assert usage.feature == "scan_read" and usage.tokens_in == 1000 and usage.cost_centavos > 0


def test_same_photo_twice_returns_same_scan_without_second_ai_call(api, manager, storage, reader):
    key = upload_photo(api, manager, storage)
    first = api.post("/scans", json={"photo_key": key}, headers=manager)
    again = api.post("/scans", json={"photo_key": key}, headers=manager)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert len(reader.calls) == 1


def test_failed_read_can_be_retried(api, db, manager, storage, reader):
    usage = AIUsageInfo(model="fake-model", input_tokens=500, output_tokens=10)
    reader.error = AIReadError(
        "Reading took too long. Please try again.", retryable=True, usage=usage
    )
    key = upload_photo(api, manager, storage)
    failed = api.post("/scans", json={"photo_key": key}, headers=manager).json()
    assert failed["status"] == "failed" and failed["retryable"] is True
    assert "too long" in failed["error_message"] and failed["lines"] == []
    assert db.scalar(select(AIUsage)).tokens_in == 500  # tokens spent are still logged

    nails, _ = _products(api, manager)
    reader.error = None
    reader.lines = [scan_line(nails["id"], unit="kg")]
    retried = api.post(f"/scans/{failed['id']}/retry", headers=manager).json()
    assert retried["status"] == "read" and retried["error_message"] is None
    assert len(retried["lines"]) == 1


def test_non_image_upload_fails_without_calling_ai(api, manager, storage, reader):
    key = upload_photo(api, manager, storage, data=b"%PDF-1.7 not a photo")
    res = api.post("/scans", json={"photo_key": key}, headers=manager).json()
    assert res["status"] == "failed" and res["retryable"] is False
    assert reader.calls == []


def test_missing_photo_fails(api, manager, reader):
    me = api.get("/auth/me", headers=manager).json()
    key = f"{me['store_id']}/scans/{'b' * 32}.jpg"
    res = api.post("/scans", json={"photo_key": key}, headers=manager).json()
    assert res["status"] == "failed" and reader.calls == []


def test_archived_product_after_reading_needs_check(api, manager, storage, reader):
    nails, _ = _products(api, manager)
    reader.lines = [scan_line(nails["id"], unit="kg")]
    key = upload_photo(api, manager, storage)
    scan = api.post("/scans", json={"photo_key": key}, headers=manager).json()
    assert scan["lines"][0]["needs_check"] is False
    api.post(f"/products/{nails['id']}/archive", headers=manager)
    again = api.get(f"/scans/{scan['id']}", headers=manager).json()
    assert again["lines"][0]["check_reasons"] == ["no_product"]


def test_archived_products_are_not_sent_to_ai(api, manager, storage, reader):
    nails, _ = _products(api, manager)
    api.post(f"/products/{nails['id']}/archive", headers=manager)
    api.post("/scans", json={"photo_key": upload_photo(api, manager, storage)}, headers=manager)
    assert [e.name for e in reader.calls[0]["catalog"]] == ["Portland Cement 40kg"]


def test_scan_stores_mapped_lines(api, db, manager, storage, reader):
    nails, _ = _products(api, manager)
    reader.lines = [scan_line(nails["id"], unit="kg")]
    key = upload_photo(api, manager, storage)
    scan_id = api.post("/scans", json={"photo_key": key}, headers=manager).json()["id"]
    stored = db.scalar(select(Scan).where(Scan.id == scan_id)).ai_result_json
    assert stored["lines"][0]["product_id"] == nails["id"]
    assert stored["raw"] == {"lines": "fake"}
