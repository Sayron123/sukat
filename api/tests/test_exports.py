"""CSV exports: managers only, own store only, every row, safe for spreadsheets."""

import csv
import io
import uuid

import pytest

from app.exports.service import BOM, pesos, safe_text
from tests.conftest import auth_header, make_product

PATHS = ["/exports/products", "/exports/transactions", "/exports/stock-movements"]


def _txn(api, headers, txn_type, lines):
    body = {"client_request_id": uuid.uuid4().hex, "type": txn_type, "lines": lines}
    res = api.post("/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _rows(res) -> list[dict[str, str]]:
    text = res.content.decode("utf-8")
    assert text.startswith(BOM)
    return list(csv.DictReader(io.StringIO(text.removeprefix(BOM))))


def _invite(api, manager, role, email):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=manager)
    token = api.post(
        "/staff/invites/accept",
        json={"token": invite.json()["token"], "password": "staff-pass-1", "full_name": role},
    ).json()["access_token"]
    return auth_header(token)


@pytest.fixture
def store(api, manager):
    """Cement ₱250.50/bag (alias "semento"): 100 in, 3 sold, then that sale voided."""
    p = make_product(api, manager, price_centavos=25050, aliases=["semento"])
    _txn(api, manager, "stock_in", [{"product_id": p["id"], "qty": "100", "unit": "bag"}])
    sale = _txn(api, manager, "sale", [{"product_id": p["id"], "qty": "3", "unit": "bag"}])
    assert api.post(f"/transactions/{sale['id']}/void", headers=manager).status_code == 200
    return {"product": p, "sale": sale}


def test_products_csv(api, manager, store):
    res = api.get("/exports/products", headers=manager)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.headers["content-disposition"].startswith('attachment; filename="sukat-products-')
    assert res.headers["cache-control"] == "no-store"
    [row] = _rows(res)
    assert row["name"] == "Portland Cement 40kg"
    assert row["other_names"] == "semento"
    assert row["price_peso"] == "250.50"
    assert row["stock_qty"] == "100"
    assert row["archived"] == "no"
    assert row["created_at"].endswith("+08:00")  # store time


def test_transactions_csv_has_one_row_per_line(api, manager, store):
    rows = _rows(api.get("/exports/transactions", headers=manager))
    assert [r["type"] for r in rows] == ["stock_in", "sale"]
    sale = rows[1]
    assert sale["transaction_id"] == store["sale"]["id"]
    assert sale["status"] == "voided"
    assert sale["voided_by"] == "Owner"
    assert sale["qty"] == "3" and sale["unit"] == "bag"
    assert sale["unit_price_peso"] == "250.50"
    assert sale["line_total_peso"] == "751.50"
    assert sale["transaction_total_peso"] == "751.50"


def test_stock_movements_csv(api, manager, store):
    rows = _rows(api.get("/exports/stock-movements", headers=manager))
    assert [(r["kind"], r["qty_change"], r["stock_after"]) for r in rows] == [
        ("stock_in", "100", "100"),
        ("sale", "-3", "97"),  # negative numbers stay numbers
        ("void", "3", "100"),
    ]
    assert rows[0]["created_by"] == "Owner"


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_can_export(api, manager, role):
    staff = _invite(api, manager, role, f"{role}@example.com")
    for path in PATHS:
        assert api.get(path, headers=staff).status_code == 403


def test_export_needs_login(api):
    for path in PATHS:
        assert api.get(path).status_code == 401


def test_export_has_only_the_callers_store(api, manager, store, signup):
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    make_product(api, other, name="Other store nails")
    for path in PATHS:
        assert "Portland" not in api.get(path, headers=other).content.decode()
    names = [r["name"] for r in _rows(api.get("/exports/products", headers=manager))]
    assert names == ["Portland Cement 40kg"]


def test_formula_text_is_made_safe(api, manager):
    make_product(api, manager, name='=HYPERLINK("http://x")', aliases=["+cmd", "@sum"])
    [row] = _rows(api.get("/exports/products", headers=manager))
    assert row["name"] == '\'=HYPERLINK("http://x")'
    assert row["other_names"] == "'+cmd; @sum"


@pytest.mark.parametrize(
    ("text", "out"),
    [("=1+1", "'=1+1"), ("-2", "'-2"), ("@x", "'@x"), ("\tx", "'\tx"), ("Nails 2in", "Nails 2in")],
)
def test_safe_text(text, out):
    assert safe_text(text) == out


@pytest.mark.parametrize(
    ("centavos", "out"), [(0, "0.00"), (5, "0.05"), (125050, "1250.50"), (-250, "-2.50")]
)
def test_pesos(centavos, out):
    assert pesos(centavos) == out


def test_empty_store_gets_headers_only(api, manager):
    for path in PATHS:
        res = api.get(path, headers=manager)
        assert res.status_code == 200
        assert _rows(res) == []
