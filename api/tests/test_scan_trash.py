import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.inventory.models import Scan
from tests.conftest import auth_header, make_product, scan_line, upload_photo


def _join(api, headers, email, role):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=headers)
    res = api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": invite.json()["token"], "password": "Staff-pass-1"},
    )
    return auth_header(res.json()["access_token"])


def _scan(api, headers, storage, reader, scan_type="sale"):
    reader.lines = [scan_line(None)]
    key = upload_photo(api, headers, storage)
    res = api.post("/scans", json={"photo_key": key, "type": scan_type}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json(), key


def _photo_exists(storage, key):
    return storage.read(key, 10_000_000) is not None


def _trash(api, headers, scan_id):
    return api.post(f"/scans/{scan_id}/trash", headers=headers)


def test_a_trashed_photo_leaves_needs_review_and_can_be_restored(api, manager, storage, reader):
    scan, key = _scan(api, manager, storage, reader)
    assert _trash(api, manager, scan["id"]).status_code == 204

    assert api.get("/reports/scans-to-review", headers=manager).json()["items"] == []
    res = api.get(f"/scans/{scan['id']}", headers=manager)
    assert res.status_code == 404 and "Recycle bin" in res.text
    assert api.post(f"/scans/{scan['id']}/rescan", headers=manager).status_code == 404
    again = api.post("/scans", json={"photo_key": key, "type": "sale"}, headers=manager)
    assert again.status_code == 404 and len(reader.calls) == 1

    [item] = api.get("/scans/trash", headers=manager).json()
    assert item["scan_id"] == scan["id"] and item["type"] == "sale" and item["line_count"] == 1
    assert item["deleted_by_name"]
    deleted_at = datetime.fromisoformat(item["deleted_at"])
    assert datetime.fromisoformat(item["delete_after"]) - deleted_at == timedelta(days=30)
    assert _photo_exists(storage, key)

    restored = api.post(f"/scans/{scan['id']}/restore", headers=manager)
    assert restored.status_code == 200 and restored.json()["status"] == "read"
    assert api.get("/scans/trash", headers=manager).json() == []
    assert len(api.get("/reports/scans-to-review", headers=manager).json()["items"]) == 1


def test_a_trashed_photo_cannot_be_saved(api, manager, storage, reader):
    cement = make_product(api, manager)
    scan, _ = _scan(api, manager, storage, reader, "stock_in")
    _trash(api, manager, scan["id"])
    res = api.post(
        "/transactions",
        json={
            "client_request_id": uuid.uuid4().hex,
            "type": "stock_in",
            "scan_id": scan["id"],
            "lines": [{"product_id": cement["id"], "qty": "1", "unit": cement["base_unit"]}],
        },
        headers=manager,
    )
    assert res.status_code == 404 and "Recycle bin" in res.text


def test_a_saved_photo_cannot_be_trashed(api, manager, storage, reader):
    cement = make_product(api, manager)
    scan, _ = _scan(api, manager, storage, reader, "stock_in")
    saved = api.post(
        "/transactions",
        json={
            "client_request_id": uuid.uuid4().hex,
            "type": "stock_in",
            "scan_id": scan["id"],
            "lines": [{"product_id": cement["id"], "qty": "1", "unit": cement["base_unit"]}],
        },
        headers=manager,
    )
    assert saved.status_code == 201, saved.text
    assert _trash(api, manager, scan["id"]).status_code == 409


def test_delete_forever_needs_the_recycle_bin_first(api, db, manager, storage, reader):
    scan, key = _scan(api, manager, storage, reader)
    assert api.delete(f"/scans/{scan['id']}", headers=manager).status_code == 404
    assert _photo_exists(storage, key)

    _trash(api, manager, scan["id"])
    assert api.delete(f"/scans/{scan['id']}", headers=manager).status_code == 204
    assert db.scalar(select(Scan)) is None
    assert not _photo_exists(storage, key)
    assert api.post(f"/scans/{scan['id']}/restore", headers=manager).status_code == 404


def test_photos_are_deleted_for_good_after_30_days(api, db, manager, storage, reader):
    old, old_key = _scan(api, manager, storage, reader)
    recent, recent_key = _scan(api, manager, storage, reader)
    _trash(api, manager, old["id"])
    _trash(api, manager, recent["id"])
    db.execute(
        update(Scan)
        .where(Scan.id == uuid.UUID(old["id"]))
        .values(deleted_at=datetime.now(UTC) - timedelta(days=30, minutes=1))
    )
    db.commit()

    items = api.get("/scans/trash", headers=manager).json()
    assert [i["scan_id"] for i in items] == [recent["id"]]
    assert not _photo_exists(storage, old_key) and _photo_exists(storage, recent_key)
    assert db.scalar(select(Scan).where(Scan.id == uuid.UUID(old["id"]))) is None


def test_members_cannot_use_the_recycle_bin(api, manager, storage, reader):
    scan, _ = _scan(api, manager, storage, reader)
    member = _join(api, manager, "m@example.com", "member")
    assert _trash(api, member, scan["id"]).status_code == 403
    assert api.get("/scans/trash", headers=member).status_code == 403

    secretary = _join(api, manager, "s@example.com", "secretary")
    assert _trash(api, secretary, scan["id"]).status_code == 204
    assert api.post(f"/scans/{scan['id']}/restore", headers=member).status_code == 403
    assert api.delete(f"/scans/{scan['id']}", headers=member).status_code == 403
    assert api.post(f"/scans/{scan['id']}/restore", headers=secretary).status_code == 200


def test_another_store_cannot_touch_the_recycle_bin(api, signup, manager, storage, reader):
    scan, _ = _scan(api, manager, storage, reader)
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    assert _trash(api, other, scan["id"]).status_code == 404
    _trash(api, manager, scan["id"])
    assert api.get("/scans/trash", headers=other).json() == []
    assert api.post(f"/scans/{scan['id']}/restore", headers=other).status_code == 404
    assert api.delete(f"/scans/{scan['id']}", headers=other).status_code == 404
