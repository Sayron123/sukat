import threading
import uuid
from decimal import Decimal

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import func, select

from app.auth.deps import get_current_member
from app.inventory.models import Scan, StockMovement, Transaction, TransactionItem
from app.inventory.schemas import TransactionIn
from app.inventory.stock_service import alias_from_raw, save_transaction
from app.products.models import Product, ProductAlias
from tests.conftest import API_BASE_URL, auth_header, make_product, scan_line, upload_photo


def _rid() -> str:
    return uuid.uuid4().hex


def _token(headers) -> str:
    return headers["Authorization"].split(" ", 1)[1]


def _stock(db, product_id) -> Decimal:
    db.expire_all()
    return db.scalar(select(Product.stock_qty).where(Product.id == product_id))


def _count(db, model) -> int:
    return db.scalar(select(func.count()).select_from(model))


@pytest.fixture
def nails(api, manager):
    return make_product(
        api,
        manager,
        name='Common Wire Nail 4"',
        category="Nails & Screws",
        base_unit="kg",
        aliases=["pako 4"],
        conversions=[{"from_unit": "box", "factor": "25"}],
    )


@pytest.fixture
def cement(api, manager):
    return make_product(api, manager, aliases=["sem"])


def _save(api, headers, lines, rid=None, scan_id=None):
    body = {"client_request_id": rid or _rid(), "type": "stock_in", "lines": lines}
    if scan_id:
        body["scan_id"] = scan_id
    return api.post("/transactions", json=body, headers=headers)


# ---------- saving ----------


def test_save_transaction_updates_stock_and_records_everything(api, db, manager, nails, cement):
    res = _save(
        api,
        manager,
        [
            {"product_id": nails["id"], "qty": "2", "unit": "box", "unit_price_centavos": 212500},
            {"product_id": nails["id"], "qty": "500", "unit": "g"},
            {"product_id": cement["id"], "qty": "10", "unit": "Sako", "unit_price_centavos": 25050},
        ],
    )
    assert res.status_code == 201, res.text
    txn = res.json()
    assert txn["total_centavos"] == 425000 + 250500
    first, second, third = txn["items"]
    assert first["qty_base"] == "50.000" and first["stock_after"] == "50.000"
    assert second["qty_base"] == "0.500" and second["stock_after"] == "50.500"
    assert third["unit"] == "bag" and third["stock_after"] == "10.000"
    assert second["line_total_centavos"] is None

    assert _stock(db, nails["id"]) == Decimal("50.5")
    assert _stock(db, cement["id"]) == Decimal("10")
    assert _count(db, StockMovement) == 3 and _count(db, TransactionItem) == 3
    assert api.get(f"/transactions/{txn['id']}", headers=manager).json() == txn
    # The product list shows the new stock too.
    assert api.get(f"/products/{nails['id']}", headers=manager).json()["stock_qty"] == "50.500"


def test_same_client_request_id_does_not_double_stock(api, db, manager, nails):
    rid = _rid()
    lines = [{"product_id": nails["id"], "qty": "1", "unit": "box"}]
    first = _save(api, manager, lines, rid)
    again = _save(api, manager, lines, rid)
    different_body = _save(
        api, manager, [{"product_id": nails["id"], "qty": "9", "unit": "box"}], rid
    )
    assert first.status_code == 201
    assert again.status_code == 200 and different_body.status_code == 200
    assert again.json() == first.json() == different_body.json()
    assert _stock(db, nails["id"]) == Decimal("25")
    assert _count(db, Transaction) == 1 and _count(db, StockMovement) == 1


def test_errors_save_nothing(api, db, manager, nails):
    res = _save(
        api,
        manager,
        [
            {"product_id": nails["id"], "qty": "1", "unit": "box"},
            {"product_id": nails["id"], "qty": "1", "unit": "drum"},  # unknown unit
        ],
    )
    assert res.status_code == 422 and "Line 2" in res.json()["detail"]
    assert _stock(db, nails["id"]) == 0
    assert _count(db, Transaction) == 0 and _count(db, StockMovement) == 0


def test_input_validation(api, manager, nails):
    for line in (
        {"product_id": nails["id"], "qty": "0", "unit": "kg"},
        {"product_id": nails["id"], "qty": "-1", "unit": "kg"},
        {"qty": "1", "unit": "kg"},  # no product
        {
            "product_id": nails["id"],
            "new_product": {"name": "X", "base_unit": "pc"},
            "qty": "1",
            "unit": "pc",
        },
    ):
        assert _save(api, manager, [line]).status_code == 422, line
    assert _save(api, manager, []).status_code == 422
    bad_id = {
        "client_request_id": "x",
        "lines": [{"product_id": nails["id"], "qty": "1", "unit": "kg"}],
    }
    assert api.post("/transactions", json=bad_id, headers=manager).status_code == 422


def test_quantity_that_rounds_to_zero_is_rejected(api, db, manager, cement):
    res = _save(api, manager, [{"product_id": cement["id"], "qty": "1", "unit": "g"}])
    assert res.status_code == 422  # 1 g = 0.000025 bag


def test_archived_product_cannot_receive_stock(api, manager, nails):
    api.post(f"/products/{nails['id']}/archive", headers=manager)
    res = _save(api, manager, [{"product_id": nails["id"], "qty": "1", "unit": "kg"}])
    assert res.status_code == 409


# ---------- new products ----------


def test_new_products_are_created_first(api, db, manager, nails):
    res = _save(
        api,
        manager,
        [
            {
                "new_product": {
                    "name": "Deformed Bar 16mm x 6m",
                    "category": "Steel",
                    "base_unit": "pc",
                },
                "qty": "20",
                "unit": "pcs",
                "unit_price_centavos": 32000,
            },
            # Same new name twice in one save -> one product.
            {
                "new_product": {"name": "deformed bar 16mm x 6m", "base_unit": "pc"},
                "qty": "5",
                "unit": "pc",
            },
            # An existing name is reused, not duplicated.
            {
                "new_product": {"name": 'COMMON WIRE NAIL 4"', "base_unit": "kg"},
                "qty": "1",
                "unit": "kg",
            },
        ],
    )
    assert res.status_code == 201, res.text
    bar_id = res.json()["items"][0]["product_id"]
    assert res.json()["items"][1]["product_id"] == bar_id
    assert res.json()["items"][2]["product_id"] == nails["id"]
    assert _stock(db, bar_id) == Decimal("25")
    assert _count(db, Product) == 2


def test_member_can_save_but_cannot_create_products(api, db, manager, nails):
    invite = api.post(
        "/staff/invites", json={"email": "m@example.com", "role": "member"}, headers=manager
    ).json()
    member = auth_header(
        api.post(
            "/staff/invites/accept",
            json={"token": invite["token"], "password": "member-pass-1", "full_name": "M"},
        ).json()["access_token"]
    )
    ok = _save(api, member, [{"product_id": nails["id"], "qty": "1", "unit": "kg"}])
    assert ok.status_code == 201
    new = _save(
        api, member, [{"new_product": {"name": "Rope", "base_unit": "m"}, "qty": "1", "unit": "m"}]
    )
    assert new.status_code == 403 and _count(db, Product) == 1


# ---------- concurrency ----------


def _run_parallel(db_sessionmaker, token, bodies):
    """Run save_transaction for each body at the same moment, each in its own thread+session."""
    barrier = threading.Barrier(len(bodies))
    errors: list[BaseException] = []
    results = []

    def work(body):
        with db_sessionmaker() as session:
            try:
                current = get_current_member(
                    session, HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
                )
                barrier.wait()
                results.append(
                    save_transaction(session, current, TransactionIn.model_validate(body))
                )
            except BaseException as e:  # noqa: BLE001 - collected and checked below
                session.rollback()
                errors.append(e)

    threads = [threading.Thread(target=work, args=(b,)) for b in bodies]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def test_concurrent_saves_count_every_delivery(db, db_sessionmaker, manager, nails):
    n = 8
    bodies = [
        {
            "client_request_id": _rid(),
            "lines": [{"product_id": nails["id"], "qty": "1", "unit": "kg"}],
        }
        for _ in range(n)
    ]
    results, errors = _run_parallel(db_sessionmaker, _token(manager), bodies)
    assert errors == [] and len(results) == n
    assert _stock(db, nails["id"]) == Decimal(n)
    afters = sorted(db.scalars(select(StockMovement.stock_after)))
    assert afters == [Decimal(i) for i in range(1, n + 1)]  # each save saw the previous one


def test_locked_read_refreshes_a_product_already_in_the_session(
    api, db, db_sessionmaker, manager, nails
):
    """If the session already holds the product (e.g. from the reuse-by-name lookup),
    the locked read must refresh it (populate_existing). Otherwise the save adds to the
    stale stock value and another save's delivery is lost."""
    with db_sessionmaker() as session:
        current = get_current_member(
            session, HTTPAuthorizationCredentials(scheme="Bearer", credentials=_token(manager))
        )
        stale = session.get(Product, uuid.UUID(nails["id"]))  # kept alive: stock 0
        other = _save(api, manager, [{"product_id": nails["id"], "qty": "5", "unit": "kg"}])
        assert other.status_code == 201
        body = {
            "client_request_id": _rid(),
            "lines": [{"product_id": nails["id"], "qty": "2", "unit": "kg"}],
        }
        save_transaction(session, current, TransactionIn.model_validate(body))
        assert stale.stock_qty == Decimal("7")  # the same object, refreshed under the lock
    assert _stock(db, nails["id"]) == Decimal("7")


def test_concurrent_repeats_of_one_request_save_once(db, db_sessionmaker, manager, nails):
    from sqlalchemy.exc import IntegrityError

    rid = _rid()
    body = {
        "client_request_id": rid,
        "lines": [{"product_id": nails["id"], "qty": "3", "unit": "kg"}],
    }
    results, errors = _run_parallel(db_sessionmaker, _token(manager), [body] * 5)
    # The endpoint turns these unique-key losses into "return the first result".
    assert all(isinstance(e, IntegrityError) for e in errors)
    assert len(results) + len(errors) == 5
    assert _stock(db, nails["id"]) == Decimal("3")
    assert _count(db, Transaction) == 1


# ---------- scans + alias learning ----------


def _scan(api, headers, storage, reader, lines):
    reader.lines = lines
    key = upload_photo(api, headers, storage)
    scan = api.post("/scans", json={"photo_key": key, "type": "stock_in"}, headers=headers).json()
    assert scan["status"] == "read"
    return scan


def test_corrected_line_teaches_an_alias(api, db, manager, storage, reader, nails, cement):
    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [
            # AI guessed cement; staff corrects to nails -> learn "pakong 4 pulgada".
            scan_line(
                cement["id"], raw_text="2 bx Pakong 4 pulgada @850", qty=Decimal("2"), unit="box"
            ),
            # AI was right -> nothing to learn.
            scan_line(cement["id"], raw_text="5 sem", qty=Decimal("5"), unit="bag"),
            # AI found nothing; staff picks cement -> learn "semento puti".
            scan_line(None, raw_text="3 sako semento puti", qty=Decimal("3"), unit="bag"),
        ],
    )
    res = _save(
        api,
        manager,
        [
            {"product_id": nails["id"], "qty": "2", "unit": "box", "scan_line": 0},
            {"product_id": cement["id"], "qty": "5", "unit": "bag", "scan_line": 1},
            {"product_id": cement["id"], "qty": "3", "unit": "bag", "scan_line": 2},
        ],
        scan_id=scan["id"],
    )
    assert res.status_code == 201, res.text
    aliases = dict(db.execute(select(ProductAlias.alias, ProductAlias.product_id)).all())
    assert str(aliases["pakong 4 pulgada"]) == nails["id"]
    assert str(aliases["semento puti"]) == cement["id"]
    assert "sem" in aliases and len(aliases) == 4  # pako 4, sem + the two learned
    assert db.scalar(select(Scan.status).where(Scan.id == scan["id"])) == "saved"
    # Search now finds nails by the learned name.
    found = api.get("/products?q=pakong 4 pulgada", headers=manager).json()["items"]
    assert [p["id"] for p in found] == [nails["id"]]


def test_alias_learning_never_steals_an_alias(api, db, manager, storage, reader, nails, cement):
    scan = _scan(api, manager, storage, reader, [scan_line(None, raw_text="1 sem", unit="kg")])
    res = _save(
        api,
        manager,
        [{"product_id": nails["id"], "qty": "1", "unit": "kg", "scan_line": 0}],
        scan_id=scan["id"],
    )
    assert res.status_code == 201
    owner = db.scalar(select(ProductAlias.product_id).where(ProductAlias.alias == "sem"))
    assert str(owner) == cement["id"]


def test_new_product_learns_raw_text_alias(api, db, manager, storage, reader):
    scan = _scan(
        api,
        manager,
        storage,
        reader,
        [
            scan_line(
                None,
                raw_text="20 pcs bakal 16",
                suggested_new_name="Deformed Bar 16mm x 6m",
                qty=Decimal("20"),
            )
        ],
    )
    res = _save(
        api,
        manager,
        [
            {
                "new_product": {
                    "name": "Deformed Bar 16mm x 6m",
                    "category": "Steel",
                    "base_unit": "pc",
                },
                "qty": "20",
                "unit": "pc",
                "scan_line": 0,
            }
        ],
        scan_id=scan["id"],
    )
    assert res.status_code == 201
    assert db.scalar(select(ProductAlias.alias)) == "bakal 16"


def test_scan_can_only_be_saved_once(api, manager, storage, reader, nails):
    scan = _scan(api, manager, storage, reader, [scan_line(nails["id"], unit="kg")])
    line = [{"product_id": nails["id"], "qty": "1", "unit": "kg", "scan_line": 0}]
    assert _save(api, manager, line, scan_id=scan["id"]).status_code == 201
    assert _save(api, manager, line, scan_id=scan["id"]).status_code == 409
    assert api.post(f"/scans/{scan['id']}/retry", headers=manager).status_code == 409


@pytest.mark.parametrize(
    ("raw", "alias"),
    [
        ("2 bx pako 4 @850", "pako 4"),
        ("2bx pako 4", "pako 4"),
        ("10 sako semento", "semento"),
        ("1 1/2 kg tie wire", "tie wire"),
        ("5 pcs bakal 10mm - P250", "bakal 10mm"),
        ("3 x hollow block 4", "hollow block 4"),
        ("  Yero   8ft  ", "yero 8ft"),
        ("12", None),
        ("2 kg", None),
        ("", None),
    ],
)
def test_alias_from_raw(raw, alias):
    assert alias_from_raw(raw) == alias


def test_app_errors_carry_http_status():
    from app.core.errors import AppError, Conflict, Forbidden, Invalid, NotFound
    from app.inventory.stock_service import ScanAlreadySaved

    assert (Invalid("x").status_code, NotFound("x").status_code) == (422, 404)
    assert (Conflict("x").status_code, Forbidden("x").status_code) == (409, 403)
    assert isinstance(ScanAlreadySaved("x"), Conflict) and isinstance(Conflict("x"), AppError)


def test_concurrent_repeats_of_a_scan_save_return_first_result(
    api, db, manager, storage, reader, nails
):
    """Same request (same client_request_id, same scan) sent 4 times at once through the
    endpoint: one save, everyone gets the same answer, never a 409."""
    from concurrent.futures import ThreadPoolExecutor

    from fastapi.testclient import TestClient

    from app.main import app

    scan = _scan(api, manager, storage, reader, [scan_line(nails["id"], unit="kg")])
    body = {
        "client_request_id": _rid(),
        "scan_id": scan["id"],
        "lines": [{"product_id": nails["id"], "qty": "3", "unit": "kg", "scan_line": 0}],
    }

    def post(_):
        with TestClient(app, base_url=API_BASE_URL) as client:
            return client.post("/transactions", json=body, headers=manager)

    with ThreadPoolExecutor(4) as pool:
        responses = list(pool.map(post, range(4)))
    assert sorted(r.status_code for r in responses) == [200, 200, 200, 201]
    assert len({r.json()["id"] for r in responses}) == 1
    assert _stock(db, nails["id"]) == Decimal("3")
