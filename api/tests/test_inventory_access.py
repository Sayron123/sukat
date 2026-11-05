"""Tenant isolation for scans, photos, transactions, and what the AI sees."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.inventory.models import Transaction
from app.products.models import Product
from tests.conftest import auth_header, make_product, scan_line, upload_photo


@pytest.fixture
def stores(api, signup, storage, reader):
    """Store A and B, each with a product, a read scan, and a saved stock-in."""
    out = {}
    for name in ("a", "b"):
        h = auth_header(signup(email=f"m-{name}@example.com", store_name=name)["access_token"])
        product = make_product(api, h, name=f"Cement {name.upper()}", base_unit="bag")
        reader.lines = [scan_line(product["id"], unit="bag")]
        key = upload_photo(api, h, storage)
        scan = api.post("/scans", json={"photo_key": key}, headers=h).json()
        txn = api.post(
            "/transactions",
            json={
                "client_request_id": uuid.uuid4().hex,
                "lines": [{"product_id": product["id"], "qty": "4", "unit": "bag"}],
            },
            headers=h,
        ).json()
        out[name] = {"h": h, "product": product, "scan": scan, "key": key, "txn": txn}
    return out


def test_cannot_read_or_retry_another_stores_scan(api, stores):
    a, b = stores["a"], stores["b"]
    assert api.get(f"/scans/{b['scan']['id']}", headers=a["h"]).status_code == 404
    assert api.post(f"/scans/{b['scan']['id']}/retry", headers=a["h"]).status_code == 404


def test_cannot_scan_another_stores_photo(api, stores, reader):
    a, b = stores["a"], stores["b"]
    calls = len(reader.calls)
    res = api.post("/scans", json={"photo_key": b["key"]}, headers=a["h"])
    assert res.status_code == 404
    assert len(reader.calls) == calls  # the AI never saw B's photo


def test_ai_only_sees_own_store_products(stores, reader):
    for call in reader.calls:
        names = {e.name for e in call["catalog"]}
        assert len(names) == 1  # each store's scan saw only its own product


def test_cannot_read_another_stores_transaction(api, stores):
    a, b = stores["a"], stores["b"]
    assert api.get(f"/transactions/{b['txn']['id']}", headers=a["h"]).status_code == 404


def test_cannot_add_stock_to_another_stores_product(api, db, stores):
    a, b = stores["a"], stores["b"]
    before = db.scalar(select(func.count()).select_from(Transaction))
    res = api.post(
        "/transactions",
        json={
            "client_request_id": uuid.uuid4().hex,
            "lines": [
                {"product_id": a["product"]["id"], "qty": "1", "unit": "bag"},
                {"product_id": b["product"]["id"], "qty": "100", "unit": "bag"},
            ],
        },
        headers=a["h"],
    )
    assert res.status_code == 404
    db.expire_all()
    stock = dict(db.execute(select(Product.name, Product.stock_qty)).all())
    assert stock == {"Cement A": Decimal("4"), "Cement B": Decimal("4")}  # nothing changed
    assert db.scalar(select(func.count()).select_from(Transaction)) == before


def test_cannot_save_another_stores_scan(api, stores):
    a, b = stores["a"], stores["b"]
    res = api.post(
        "/transactions",
        json={
            "client_request_id": uuid.uuid4().hex,
            "scan_id": b["scan"]["id"],
            "lines": [
                {"product_id": a["product"]["id"], "qty": "1", "unit": "bag", "scan_line": 0}
            ],
        },
        headers=a["h"],
    )
    assert res.status_code == 404


def test_same_client_request_id_in_two_stores_are_separate(api, stores):
    a, b = stores["a"], stores["b"]
    rid = uuid.uuid4().hex
    for s in (a, b):
        res = api.post(
            "/transactions",
            json={
                "client_request_id": rid,
                "lines": [{"product_id": s["product"]["id"], "qty": "1", "unit": "bag"}],
            },
            headers=s["h"],
        )
        assert res.status_code == 201  # idempotency is per store


def test_upload_keys_are_per_store(api, stores):
    a, b = stores["a"], stores["b"]
    a_store = api.get("/auth/me", headers=a["h"]).json()["store_id"]
    assert a["key"].startswith(f"{a_store}/") and not b["key"].startswith(f"{a_store}/")
