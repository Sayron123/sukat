"""Saving sales: stock goes down, default prices, negative-stock confirm, idempotency."""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.inventory.models import StockMovement, Transaction
from app.products.models import Product, ProductAlias
from tests.conftest import auth_header, make_product, scan_line, upload_photo


def _rid() -> str:
    return uuid.uuid4().hex


def _stock(db, product_id) -> Decimal:
    db.expire_all()
    return db.scalar(select(Product.stock_qty).where(Product.id == product_id))


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


def _txn(api, headers, txn_type, lines, rid=None, **extra):
    body = {"client_request_id": rid or _rid(), "type": txn_type, "lines": lines, **extra}
    return api.post("/transactions", json=body, headers=headers)


@pytest.fixture
def nails(api, manager):
    """Nails priced ₱85/kg, 1 box = 25 kg, with 100 kg in stock."""
    p = make_product(
        api,
        manager,
        name='Common Wire Nail 4"',
        category="Nails & Screws",
        base_unit="kg",
        price_centavos=8500,
        aliases=["pako 4"],
        conversions=[{"from_unit": "box", "factor": "25"}],
    )
    res = _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "4", "unit": "box"}])
    assert res.status_code == 201
    return p


@pytest.fixture
def cement(api, manager):
    """Cement ₱250/bag, 10 bags in stock."""
    p = make_product(api, manager, price_centavos=25000, aliases=["sem"])
    _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "10", "unit": "bag"}])
    return p


def test_sale_reduces_stock(api, db, manager, nails, cement):
    res = _txn(
        api,
        manager,
        "sale",
        [
            {"product_id": nails["id"], "qty": "1", "unit": "box"},  # 25 kg, no price written
            {"product_id": nails["id"], "qty": "500", "unit": "g"},
            {"product_id": cement["id"], "qty": "3", "unit": "bag", "unit_price_centavos": 26000},
        ],
    )
    assert res.status_code == 201, res.text
    sale = res.json()
    assert sale["type"] == "sale"
    box, grams, bags = sale["items"]
    assert box["qty_base"] == "25.000" and box["stock_after"] == "75.000"
    assert box["unit_price_centavos"] == 212500  # product price for one box
    assert grams["stock_after"] == "74.500" and grams["line_total_centavos"] == 4250
    assert bags["unit_price_centavos"] == 26000 and bags["stock_after"] == "7.000"
    assert sale["total_centavos"] == 212500 + 4250 + 78000

    assert _stock(db, nails["id"]) == Decimal("74.5")
    assert _stock(db, cement["id"]) == Decimal("7")
    changes = sorted(
        db.scalars(
            select(StockMovement.qty_change).where(StockMovement.transaction_id == sale["id"])
        )
    )
    assert changes == [Decimal("-25"), Decimal("-3"), Decimal("-0.5")]


def test_same_client_request_id_does_not_reduce_twice(api, db, manager, cement):
    rid = _rid()
    line = [{"product_id": cement["id"], "qty": "2", "unit": "bag"}]
    first = _txn(api, manager, "sale", line, rid)
    again = _txn(api, manager, "sale", line, rid)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json() == first.json()
    assert _stock(db, cement["id"]) == Decimal("8")


def test_negative_stock_needs_confirm(api, db, manager, nails, cement):
    rid = _rid()
    lines = [
        {"product_id": cement["id"], "qty": "12", "unit": "bag"},  # only 10 in stock
        {"product_id": nails["id"], "qty": "1", "unit": "kg"},  # fine
    ]
    refused = _txn(api, manager, "sale", lines, rid)
    assert refused.status_code == 409
    body = refused.json()
    assert body["code"] == "negative_stock"
    assert body["products"] == [
        {
            "product_id": cement["id"],
            "name": "Portland Cement 40kg",
            "base_unit": "bag",
            "stock": "10.000",
            "stock_after": "-2.000",
        }
    ]
    # Nothing was saved, so the same request id can be sent again with confirm.
    assert _stock(db, cement["id"]) == Decimal("10") and _stock(db, nails["id"]) == Decimal("100")
    assert (
        db.scalar(select(func.count()).select_from(Transaction).where(Transaction.type == "sale"))
        == 0
    )

    confirmed = _txn(api, manager, "sale", lines, rid, confirm=True)
    assert confirmed.status_code == 201
    assert _stock(db, cement["id"]) == Decimal("-2")


def test_two_lines_of_one_product_count_together_for_negative_stock(api, manager, cement):
    lines = [
        {"product_id": cement["id"], "qty": "6", "unit": "bag"},
        {"product_id": cement["id"], "qty": "6", "unit": "bag"},
    ]
    assert _txn(api, manager, "sale", lines).status_code == 409


def test_sale_cannot_create_products(api, manager):
    res = _txn(
        api,
        manager,
        "sale",
        [{"new_product": {"name": "Rope", "base_unit": "m"}, "qty": "1", "unit": "m"}],
    )
    assert res.status_code == 422


def test_unpriced_product_sells_without_price(api, manager):
    p = make_product(api, manager, name="Rope", category="Others", base_unit="m")
    _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "10", "unit": "m"}])
    res = _txn(api, manager, "sale", [{"product_id": p["id"], "qty": "2", "unit": "m"}])
    assert res.status_code == 201
    assert (
        res.json()["items"][0]["unit_price_centavos"] is None and res.json()["total_centavos"] == 0
    )


def test_member_can_record_a_sale(api, manager, cement):
    invite = api.post(
        "/staff/invites", json={"email": "m@example.com", "role": "member"}, headers=manager
    ).json()
    member = auth_header(
        api.post(
            "/staff/invites/accept",
            json={"token": invite["token"], "password": "Member-pass-1", "full_name": "M"},
        ).json()["access_token"]
    )
    res = _txn(api, member, "sale", [{"product_id": cement["id"], "qty": "1", "unit": "bag"}])
    assert res.status_code == 201


def _scan(api, headers, storage, reader, lines, scan_type):
    reader.lines = lines
    key = upload_photo(api, headers, storage)
    return api.post("/scans", json={"photo_key": key, "type": scan_type}, headers=headers).json()


def test_scan_type_must_match_transaction_type(api, manager, storage, reader, cement):
    scan = _scan(api, manager, storage, reader, [scan_line(cement["id"], unit="bag")], "stock_in")
    res = _txn(
        api,
        manager,
        "sale",
        [{"product_id": cement["id"], "qty": "1", "unit": "bag", "scan_line": 0}],
        scan_id=scan["id"],
    )
    assert res.status_code == 409 and "stock-in list" in res.json()["detail"]


def test_sale_from_scan_learns_alias_and_marks_scan_saved(api, db, manager, storage, reader, nails):
    from app.inventory.models import Scan

    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [scan_line(None, raw_text="2 kg pakong bakal 4", qty=Decimal("2"), unit="kg")],
        "sale",
    )
    res = _txn(
        api,
        manager,
        "sale",
        [{"product_id": nails["id"], "qty": "2", "unit": "kg", "scan_line": 0}],
        scan_id=scan["id"],
    )
    assert res.status_code == 201
    owner = db.scalar(select(ProductAlias.product_id).where(ProductAlias.alias == "pakong bakal 4"))
    assert str(owner) == nails["id"]
    assert db.scalar(select(Scan.status).where(Scan.id == scan["id"])) == "saved"


def test_member_sale_from_scan_learns_no_alias(api, db, manager, storage, reader, nails):
    # Audit M1 (Phase 4 part): only managers and secretaries teach aliases.
    invite = api.post(
        "/staff/invites", json={"email": "m@example.com", "role": "member"}, headers=manager
    ).json()
    member = auth_header(
        api.post(
            "/staff/invites/accept",
            json={"token": invite["token"], "password": "Member-pass-1", "full_name": "M"},
        ).json()["access_token"]
    )
    scan = _scan(
        api,
        member,
        storage,
        reader,
        [scan_line(None, raw_text="2 kg pakong bakal 4", qty=Decimal("2"), unit="kg")],
        "sale",
    )
    res = _txn(
        api,
        member,
        "sale",
        [{"product_id": nails["id"], "qty": "2", "unit": "kg", "scan_line": 0}],
        scan_id=scan["id"],
    )
    assert res.status_code == 201, res.text  # the sale still saves
    assert db.scalar(select(ProductAlias).where(ProductAlias.alias == "pakong bakal 4")) is None


# ---------- tenant isolation ----------


@pytest.fixture
def two_stores(api, signup, storage, reader):
    out = {}
    for name in ("a", "b"):
        h = auth_header(signup(email=f"m-{name}@example.com", store_name=name)["access_token"])
        p = make_product(
            api, h, name=f"Cement {name.upper()}", base_unit="bag", price_centavos=25000
        )
        _txn(api, h, "stock_in", [{"product_id": p["id"], "qty": "10", "unit": "bag"}])
        sale = _txn(api, h, "sale", [{"product_id": p["id"], "qty": "1", "unit": "bag"}]).json()
        scan = _scan(api, h, storage, reader, [scan_line(p["id"], unit="bag")], "sale")
        out[name] = {"h": h, "product": p, "sale": sale, "scan": scan}
    return out


def test_cannot_sell_another_stores_product(api, db, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    res = _txn(
        api,
        a["h"],
        "sale",
        [
            {"product_id": a["product"]["id"], "qty": "1", "unit": "bag"},
            {"product_id": b["product"]["id"], "qty": "5", "unit": "bag"},
        ],
    )
    assert res.status_code == 404
    assert _stock(db, a["product"]["id"]) == Decimal("9")  # whole sale rolled back
    assert _stock(db, b["product"]["id"]) == Decimal("9")


def test_cannot_read_or_save_another_stores_sale_or_scan(api, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    assert api.get(f"/transactions/{b['sale']['id']}", headers=a["h"]).status_code == 404
    assert api.get(f"/scans/{b['scan']['id']}", headers=a["h"]).status_code == 404
    res = _txn(
        api,
        a["h"],
        "sale",
        [{"product_id": a["product"]["id"], "qty": "1", "unit": "bag", "scan_line": 0}],
        scan_id=b["scan"]["id"],
    )
    assert res.status_code == 404


def test_transaction_list_is_per_store(api, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    ids = {t["id"] for t in api.get("/transactions", headers=a["h"]).json()["items"]}
    assert a["sale"]["id"] in ids and b["sale"]["id"] not in ids


# ---------- concurrency ----------


def test_concurrent_sales_all_count(db, db_sessionmaker, manager, cement):
    import threading

    from fastapi.security import HTTPAuthorizationCredentials

    from app.auth.deps import get_current_member
    from app.inventory.schemas import TransactionIn
    from app.inventory.stock_service import save_transaction

    token = manager["Authorization"].split(" ", 1)[1]
    n = 6
    barrier = threading.Barrier(n)
    errors: list[BaseException] = []

    def work():
        with db_sessionmaker() as session:
            try:
                current = get_current_member(
                    session, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
                )
                body = TransactionIn.model_validate(
                    {
                        "client_request_id": _rid(),
                        "type": "sale",
                        "lines": [{"product_id": cement["id"], "qty": "1", "unit": "bag"}],
                    }
                )
                barrier.wait()
                save_transaction(session, current, body)
            except BaseException as e:  # noqa: BLE001 - checked below
                session.rollback()
                errors.append(e)

    threads = [threading.Thread(target=work) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert errors == []
    assert _stock(db, cement["id"]) == Decimal(10 - n)
    afters = sorted(
        db.scalars(select(StockMovement.stock_after).where(StockMovement.qty_change < 0))
    )
    assert afters == [Decimal(i) for i in range(10 - n, 10)]  # each sale saw the previous


def test_refused_sale_releases_its_locks_immediately(db_sessionmaker, manager, cement):
    """After a negative_stock refusal, the product row must not stay locked while the
    request's session is still open, or the phone's 'Save anyway' would have to wait."""
    from fastapi.security import HTTPAuthorizationCredentials
    from sqlalchemy import text

    from app.auth.deps import get_current_member
    from app.core.errors import AppError
    from app.inventory.schemas import TransactionIn
    from app.inventory.stock_service import save_transaction_once

    token = manager["Authorization"].split(" ", 1)[1]
    with db_sessionmaker() as a, db_sessionmaker() as b:
        current = get_current_member(
            a, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        )
        body = TransactionIn.model_validate(
            {
                "client_request_id": _rid(),
                "type": "sale",
                "lines": [{"product_id": cement["id"], "qty": "99", "unit": "bag"}],
            }
        )
        with pytest.raises(AppError) as refused:
            save_transaction_once(a, current, body)
        assert refused.value.code == "negative_stock"
        # Session `a` is still open. NOWAIT fails at once if the row is still locked.
        b.execute(
            text("SELECT 1 FROM products WHERE id = :id FOR UPDATE NOWAIT"), {"id": cement["id"]}
        )
        b.rollback()
