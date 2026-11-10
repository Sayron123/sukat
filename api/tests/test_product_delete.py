import uuid

import pytest
from sqlalchemy import text

from app.products.constants import MAX_BULK_DELETE
from tests.conftest import auth_header, make_product


def _join(api, headers, email, role):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=headers)
    res = api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": invite.json()["token"], "password": "Staff-pass-1"},
    )
    return auth_header(res.json()["access_token"])


def _stock_in(api, headers, product):
    res = api.post(
        "/transactions",
        json={
            "client_request_id": uuid.uuid4().hex,
            "type": "stock_in",
            "lines": [{"product_id": product["id"], "qty": "5", "unit": product["base_unit"]}],
        },
        headers=headers,
    )
    assert res.status_code == 201, res.text


def _bulk(api, headers, ids):
    return api.post("/products/bulk-delete", json={"ids": ids}, headers=headers)


def _product(api, headers, name):
    return make_product(api, headers, name=name)


def test_manager_deletes_an_unused_product_and_its_aliases(api, db, manager):
    product = make_product(api, manager, aliases=["sem"])
    assert api.delete(f"/products/{product['id']}", headers=manager).status_code == 204
    assert api.get(f"/products/{product['id']}", headers=manager).status_code == 404
    assert db.scalar(text("SELECT count(*) FROM product_aliases")) == 0


def test_deleting_a_missing_product_is_not_found(api, manager):
    assert api.delete(f"/products/{uuid.uuid4()}", headers=manager).status_code == 404


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_can_delete(api, manager, role):
    product = make_product(api, manager)
    other = _join(api, manager, "staff@example.com", role)
    assert api.delete(f"/products/{product['id']}", headers=other).status_code == 403
    assert _bulk(api, other, [product["id"]]).status_code == 403
    assert api.get("/products/ids", headers=other).status_code == 403
    assert api.get(f"/products/{product['id']}", headers=manager).status_code == 200


def test_deleting_needs_sign_in(api):
    assert api.delete(f"/products/{uuid.uuid4()}").status_code == 401


def test_a_product_with_history_cannot_be_deleted(api, manager):
    product = make_product(api, manager)
    _stock_in(api, manager, product)
    res = api.delete(f"/products/{product['id']}", headers=manager)
    assert res.status_code == 409 and "Archive it instead" in res.text
    assert api.get(f"/products/{product['id']}", headers=manager).json()["stock_qty"] == "5.000"


def test_bulk_delete_keeps_products_with_history(api, manager):
    used = _product(api, manager, "Used Item")
    _stock_in(api, manager, used)
    unused = [_product(api, manager, f"Item {i}")["id"] for i in range(3)]
    res = _bulk(api, manager, [*unused, used["id"], unused[0]])
    assert res.status_code == 200
    assert res.json() == {"deleted": 3, "kept": ["Used Item"]}
    left = api.get("/products", headers=manager).json()["items"]
    assert [p["id"] for p in left] == [used["id"]]


def test_delete_cannot_reach_another_store(api, signup, manager):
    other = auth_header(signup(email="b@example.com", store_name="B")["access_token"])
    product = make_product(api, other)
    assert api.delete(f"/products/{product['id']}", headers=manager).status_code == 404
    assert _bulk(api, manager, [product["id"]]).json() == {"deleted": 0, "kept": []}
    assert api.get(f"/products/{product['id']}", headers=other).status_code == 200


def test_select_all_follows_the_filters_and_every_page(api, manager):
    for i in range(25):
        _product(api, manager, f"Nail {i:02}")
    cement = make_product(api, manager, name="Cement", category="Cement")
    archived = _product(api, manager, "Old Nail")
    api.post(f"/products/{archived['id']}/archive", headers=manager)
    assert len(api.get("/products/ids", headers=manager).json()) == 26
    assert api.get("/products/ids?q=cement", headers=manager).json() == [cement["id"]]
    assert api.get("/products/ids?category=Cement", headers=manager).json() != []
    assert archived["id"] not in api.get("/products/ids", headers=manager).json()


def test_a_deleted_starter_item_can_be_imported_again(api, manager):
    key = api.get("/products/catalog", headers=manager).json()[0]["key"]
    assert (
        api.post("/products/import", json={"keys": [key]}, headers=manager).json()["created"] == 1
    )
    ids = api.get("/products/ids", headers=manager).json()
    assert _bulk(api, manager, ids).json()["deleted"] == 1
    assert (
        api.post("/products/import", json={"keys": [key]}, headers=manager).json()["created"] == 1
    )


@pytest.mark.parametrize("count", [0, MAX_BULK_DELETE + 1])
def test_bulk_delete_has_size_limits(api, manager, count):
    ids = [str(uuid.uuid4()) for _ in range(count)]
    assert _bulk(api, manager, ids).status_code == 422
