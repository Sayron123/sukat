"""Voiding transactions: stock restored exactly once, nothing deleted, who/when recorded."""

import threading
import uuid
from decimal import Decimal

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select

from app.auth.deps import get_current_member
from app.core.errors import AppError
from app.inventory.models import StockMovement, Transaction, TransactionItem
from app.inventory.stock_service import void_transaction
from app.products.models import Product
from tests.conftest import auth_header, make_product


def _stock(db, pid) -> Decimal:
    db.expire_all()
    return db.scalar(select(Product.stock_qty).where(Product.id == pid))


def _txn(api, headers, txn_type, lines, **extra):
    body = {"client_request_id": uuid.uuid4().hex, "type": txn_type, "lines": lines, **extra}
    res = api.post("/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _join(api, manager, role):
    invite = api.post(
        "/staff/invites", json={"email": f"{role}@example.com", "role": role}, headers=manager
    ).json()
    token = api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
            "token": invite["token"],
            "password": "Staff-pass-1",
            "full_name": role.title(),
        },
    ).json()["access_token"]
    return auth_header(token)


@pytest.fixture
def cement(api, manager):
    p = make_product(api, manager, price_centavos=25000)
    _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "10", "unit": "bag"}])
    return p


def test_void_sale_restores_stock_exactly_once(api, db, manager, cement):
    sale = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "3", "unit": "bag"}])
    assert _stock(db, cement["id"]) == Decimal("7")

    res = api.post(f"/transactions/{sale['id']}/void", headers=manager)
    assert res.status_code == 200, res.text
    voided = res.json()
    assert voided["status"] == "voided" and voided["voided_by_name"] == "Owner"
    assert voided["voided_at"] is not None
    assert voided["items"][0]["stock_after"] == "7.000"  # the original line, unchanged
    assert _stock(db, cement["id"]) == Decimal("10")

    again = api.post(f"/transactions/{sale['id']}/void", headers=manager)
    assert again.status_code == 409 and again.json()["code"] == "already_voided"
    assert _stock(db, cement["id"]) == Decimal("10")


def test_void_keeps_everything_and_adds_reversals(api, db, manager, cement):
    sale = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "2", "unit": "bag"}])
    api.post(f"/transactions/{sale['id']}/void", headers=manager)
    rows = db.execute(
        select(StockMovement.qty_change, StockMovement.stock_after, StockMovement.is_reversal)
        .where(StockMovement.transaction_id == sale["id"])
        .order_by(StockMovement.is_reversal)
    ).all()
    assert rows == [(Decimal("-2"), Decimal("8"), False), (Decimal("2"), Decimal("10"), True)]
    assert db.scalar(select(func.count()).select_from(TransactionItem)) == 2  # nothing deleted
    assert api.get(f"/transactions/{sale['id']}", headers=manager).json()["status"] == "voided"


def test_void_stock_in_takes_stock_back_out(api, db, manager, cement):
    delivery = _txn(
        api, manager, "stock_in", [{"product_id": cement["id"], "qty": "5", "unit": "bag"}]
    )
    assert _stock(db, cement["id"]) == Decimal("15")
    api.post(f"/transactions/{delivery['id']}/void", headers=manager)
    assert _stock(db, cement["id"]) == Decimal("10")


def test_void_restores_against_current_stock(api, db, manager, cement):
    """Other sales after the voided one stay counted."""
    first = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "3", "unit": "bag"}])
    _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "4", "unit": "bag"}])
    api.post(f"/transactions/{first['id']}/void", headers=manager)
    assert _stock(db, cement["id"]) == Decimal("6")  # 10 - 3 - 4 + 3


def test_secretary_can_void_member_cannot(api, db, manager, cement):
    sale = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "1", "unit": "bag"}])
    member = _join(api, manager, "member")
    assert api.post(f"/transactions/{sale['id']}/void", headers=member).status_code == 403
    assert _stock(db, cement["id"]) == Decimal("9")
    secretary = _join(api, manager, "secretary")
    res = api.post(f"/transactions/{sale['id']}/void", headers=secretary)
    assert res.status_code == 200 and res.json()["voided_by_name"] == "Secretary"


def test_cannot_void_another_stores_transaction(api, db, signup):
    a = auth_header(signup(email="a@example.com", store_name="A")["access_token"])
    b = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    pb = make_product(api, b, name="B cement", base_unit="bag")
    txn_b = _txn(api, b, "stock_in", [{"product_id": pb["id"], "qty": "4", "unit": "bag"}])
    assert api.post(f"/transactions/{txn_b['id']}/void", headers=a).status_code == 404
    assert _stock(db, pb["id"]) == Decimal("4")
    assert db.scalar(select(Transaction.status).where(Transaction.id == txn_b["id"])) == "saved"


def test_two_voids_at_the_same_moment_restore_once(api, db, db_sessionmaker, manager, cement):
    sale = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "4", "unit": "bag"}])
    token = manager["Authorization"].split(" ", 1)[1]
    barrier = threading.Barrier(4)
    outcomes: list[str] = []

    def work():
        with db_sessionmaker() as session:
            current = get_current_member(
                session, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            )
            barrier.wait()
            try:
                void_transaction(session, current, uuid.UUID(sale["id"]))
                outcomes.append("voided")
            except AppError as e:
                session.rollback()
                outcomes.append(e.code or type(e).__name__)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert sorted(outcomes) == ["already_voided"] * 3 + ["voided"]
    assert _stock(db, cement["id"]) == Decimal("10")


def test_transaction_list_shows_newest_first_with_status(api, manager, cement):
    sale = _txn(api, manager, "sale", [{"product_id": cement["id"], "qty": "1", "unit": "bag"}])
    api.post(f"/transactions/{sale['id']}/void", headers=manager)
    page = api.get("/transactions", headers=manager).json()
    assert page["total"] == 2
    assert [(t["type"], t["status"], t["item_count"]) for t in page["items"]] == [
        ("sale", "voided", 1),
        ("stock_in", "saved", 1),
    ]
    sales = api.get("/transactions?type=sale", headers=manager).json()
    assert sales["total"] == 1 and sales["items"][0]["total_centavos"] == 25000
