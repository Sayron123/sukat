from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.models import AIUsage
from app.inventory.models import Scan
from tests.conftest import make_product, scan_line, upload_photo


def _scan(api, headers, storage, reader, lines, scan_type="stock_in"):
    reader.lines = lines
    key = upload_photo(api, headers, storage)
    return api.post("/scans", json={"photo_key": key, "type": scan_type}, headers=headers)


def _cement(api, headers):
    return make_product(api, headers, price_centavos=25000)


def test_a_photo_with_no_items_leaves_nothing_behind(api, db, manager, storage, reader):
    res = _scan(api, manager, storage, reader, [])
    body = res.json()
    assert res.status_code == 201
    assert body["status"] == "empty" and body["lines"] == [] and body["can_rescan"] is False
    assert "No items" in body["error_message"]
    assert db.scalar(select(Scan)) is None
    assert api.get(f"/scans/{body['id']}", headers=manager).status_code == 404
    assert db.scalar(select(AIUsage)) is not None
    review = api.get("/reports/scans-to-review", headers=manager).json()
    assert review["items"] == []


def test_a_photo_can_be_scanned_again_once(api, manager, storage, reader):
    cement = _cement(api, manager)
    first = _scan(api, manager, storage, reader, [scan_line(None, raw_text="??")]).json()
    assert first["can_rescan"] is True

    reader.lines = [scan_line(cement["id"], unit="bag", qty=Decimal("3"))]
    again = api.post(f"/scans/{first['id']}/rescan", headers=manager)
    assert again.status_code == 200
    body = again.json()
    assert body["id"] == first["id"] and body["can_rescan"] is False
    assert [line["product_id"] for line in body["lines"]] == [cement["id"]]
    assert len(reader.calls) == 2

    third = api.post(f"/scans/{first['id']}/rescan", headers=manager)
    assert third.status_code == 409 and len(reader.calls) == 2


def test_a_rescan_that_finds_nothing_removes_the_scan(api, db, manager, storage, reader):
    first = _scan(api, manager, storage, reader, [scan_line(None)]).json()
    reader.lines = []
    body = api.post(f"/scans/{first['id']}/rescan", headers=manager).json()
    assert body["status"] == "empty"
    assert db.scalar(select(Scan)) is None


def test_only_a_scan_waiting_for_review_can_be_rescanned(api, manager, storage, reader):
    cement = _cement(api, manager)
    scan = _scan(api, manager, storage, reader, [scan_line(cement["id"], unit="bag")]).json()
    saved = api.post(
        "/transactions",
        json={
            "client_request_id": "a" * 32,
            "type": "stock_in",
            "scan_id": scan["id"],
            "lines": [{"product_id": cement["id"], "qty": "1", "unit": "bag"}],
        },
        headers=manager,
    )
    assert saved.status_code == 201, saved.text
    assert api.post(f"/scans/{scan['id']}/rescan", headers=manager).status_code == 409
    assert (
        api.patch(f"/scans/{scan['id']}", json={"type": "sale"}, headers=manager).status_code == 409
    )


def test_switching_to_sale_applies_sale_rules_and_back(api, manager, storage, reader):
    cement = _cement(api, manager)
    lines = [
        scan_line(cement["id"], unit="bag", qty=Decimal("2")),
        scan_line(None, raw_text="5 bakal 16", suggested_new_name="Deformed Bar 16mm x 6m"),
    ]
    scan = _scan(api, manager, storage, reader, lines).json()
    assert scan["lines"][0]["unit_price_centavos"] is None
    assert scan["lines"][1]["is_new"] is True

    sale = api.patch(f"/scans/{scan['id']}", json={"type": "sale"}, headers=manager)
    assert sale.status_code == 200
    cement_line, unknown = sale.json()["lines"]
    assert sale.json()["type"] == "sale"
    assert cement_line["unit_price_centavos"] == 25000 and cement_line["price_source"] == "product"
    assert unknown["is_new"] is False and unknown["check_reasons"] == ["no_product"]

    back = api.patch(f"/scans/{scan['id']}", json={"type": "stock_in"}, headers=manager).json()
    assert back["type"] == "stock_in" and back["lines"][1]["is_new"] is True
    assert back["lines"][1]["suggested_new_name"] == "Deformed Bar 16mm x 6m"


def test_a_switched_scan_saves_as_its_new_type(api, manager, storage, reader):
    cement = _cement(api, manager)
    scan = _scan(api, manager, storage, reader, [scan_line(cement["id"], unit="bag")]).json()
    api.patch(f"/scans/{scan['id']}", json={"type": "sale"}, headers=manager)
    res = api.post(
        "/transactions",
        json={
            "client_request_id": "b" * 32,
            "type": "stock_in",
            "scan_id": scan["id"],
            "lines": [{"product_id": cement["id"], "qty": "1", "unit": "bag"}],
        },
        headers=manager,
    )
    assert res.status_code == 409 and "sale receipt" in res.text


@pytest.mark.parametrize("body", [{"type": "adjustment"}, {"type": "sale", "x": 1}, {}])
def test_switching_needs_a_valid_type(api, manager, storage, reader, body):
    scan = _scan(api, manager, storage, reader, [scan_line(None)]).json()
    assert api.patch(f"/scans/{scan['id']}", json=body, headers=manager).status_code == 422


def test_another_store_cannot_switch_or_rescan(api, signup, manager, storage, reader):
    from tests.conftest import auth_header

    scan = _scan(api, manager, storage, reader, [scan_line(None)]).json()
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    assert (
        api.patch(f"/scans/{scan['id']}", json={"type": "sale"}, headers=other).status_code == 404
    )
    assert api.post(f"/scans/{scan['id']}/rescan", headers=other).status_code == 404
