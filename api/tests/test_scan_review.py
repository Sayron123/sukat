from decimal import Decimal

import pytest
from sqlalchemy import select

from app.ai.errors import AIReadError
from app.ai.models import AIUsage
from app.inventory.models import Scan
from app.inventory.scan_service import RESCAN_FAILED, RESCAN_FOUND_NOTHING
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
    assert list(storage.root.rglob("*.jpg")) == []
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


def test_a_rescan_that_finds_nothing_keeps_the_first_read(api, db, manager, storage, reader):
    cement = _cement(api, manager)
    first = _scan(api, manager, storage, reader, [scan_line(cement["id"], unit="bag")]).json()
    reader.lines = []
    res = api.post(f"/scans/{first['id']}/rescan", headers=manager)
    assert res.status_code == 409
    assert res.json() == {"detail": RESCAN_FOUND_NOTHING, "code": "first_read_kept"}

    kept = api.get(f"/scans/{first['id']}", headers=manager).json()
    assert kept["status"] == "read" and kept["can_rescan"] is False
    assert kept["lines"] == first["lines"]
    assert len(db.scalars(select(AIUsage)).all()) == 2
    assert len(list(storage.root.rglob("*.jpg"))) == 1


@pytest.mark.parametrize(("retryable", "can_rescan"), [(True, True), (False, False)])
def test_a_rescan_that_fails_keeps_the_first_read(
    api, manager, storage, reader, retryable, can_rescan
):
    cement = _cement(api, manager)
    first = _scan(api, manager, storage, reader, [scan_line(cement["id"], unit="bag")]).json()
    reader.error = AIReadError("The reader is busy. Please try again.", retryable=retryable)
    res = api.post(f"/scans/{first['id']}/rescan", headers=manager)
    assert res.status_code == 409
    assert res.json() == {"detail": RESCAN_FAILED, "code": "first_read_kept"}

    kept = api.get(f"/scans/{first['id']}", headers=manager).json()
    assert kept["status"] == "read" and kept["can_rescan"] is can_rescan
    assert kept["lines"] == first["lines"]

    body = {
        "client_request_id": "rescan-kept-1",
        "type": "stock_in",
        "scan_id": first["id"],
        "lines": [{"product_id": cement["id"], "qty": "1", "unit": "bag", "scan_line": 0}],
    }
    assert api.post("/transactions", json=body, headers=manager).status_code == 201


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


def test_another_store_cannot_rescan(api, signup, manager, storage, reader):
    from tests.conftest import auth_header

    scan = _scan(api, manager, storage, reader, [scan_line(None)]).json()
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    assert api.post(f"/scans/{scan['id']}/rescan", headers=other).status_code == 404
