"""Products: tenant isolation (Store A vs B), roles, alias search, and pagination."""

import pytest
from sqlalchemy import select

from app.products.models import Product
from tests.conftest import auth_header, make_product


def _join(api, manager_headers, email, role):
    invite = api.post(
        "/staff/invites", json={"email": email, "role": role}, headers=manager_headers
    ).json()
    res = api.post(
        "/staff/invites/accept",
        json={"token": invite["token"], "password": "staff-pass-1", "full_name": role},
    )
    return auth_header(res.json()["access_token"])


@pytest.fixture
def stores(api, signup):
    """Two stores, each with one product that has the alias "sem"."""
    out = {}
    for name in ("a", "b"):
        headers = auth_header(
            signup(email=f"m-{name}@example.com", store_name=name)["access_token"]
        )
        product = make_product(api, headers, aliases=["sem"])  # same name AND alias in both
        out[name] = {"headers": headers, "product": product}
    return out


# ---------- tenant isolation ----------


def test_store_a_cannot_see_store_b_product(api, stores):
    a, b = stores["a"], stores["b"]
    pid = b["product"]["id"]
    assert api.get(f"/products/{pid}", headers=a["headers"]).status_code == 404
    listed = api.get("/products?include_archived=true", headers=a["headers"]).json()
    assert [p["id"] for p in listed["items"]] == [a["product"]["id"]]
    searched = api.get("/products?q=sem", headers=a["headers"]).json()
    assert [p["id"] for p in searched["items"]] == [a["product"]["id"]]


def test_store_a_cannot_edit_or_archive_store_b_product(api, db, stores):
    a, b = stores["a"], stores["b"]
    pid = b["product"]["id"]
    h = a["headers"]
    assert api.patch(f"/products/{pid}", json={"name": "Hacked"}, headers=h).status_code == 404
    assert api.post(f"/products/{pid}/archive", headers=h).status_code == 404
    assert api.post(f"/products/{pid}/unarchive", headers=h).status_code == 404
    product = db.scalar(select(Product).where(Product.id == pid))
    assert product.name == "Portland Cement 40kg" and product.archived is False


def test_same_name_and_alias_are_allowed_in_different_stores(stores):
    assert stores["a"]["product"]["name"] == stores["b"]["product"]["name"]
    assert stores["a"]["product"]["aliases"] == stores["b"]["product"]["aliases"] == ["sem"]


def test_cannot_create_into_another_store_via_body(api, stores):
    res = api.post(
        "/products",
        json={
            "name": "X",
            "category": "Others",
            "base_unit": "pc",
            "store_id": stores["b"]["product"]["id"],
        },
        headers=stores["a"]["headers"],
    )
    assert res.status_code == 422  # unknown fields are rejected, never used


def test_import_only_affects_own_store(api, stores):
    a, b = stores["a"], stores["b"]
    api.post("/products/import", json={"keys": ["hollow-block-4in"]}, headers=a["headers"])
    assert api.get("/products", headers=a["headers"]).json()["total"] == 2
    assert api.get("/products", headers=b["headers"]).json()["total"] == 1
    b_catalog = api.get("/products/catalog", headers=b["headers"]).json()
    assert not next(i for i in b_catalog if i["key"] == "hollow-block-4in")["already_in_store"]


# ---------- roles ----------


def test_member_is_read_only(api, stores):
    manager = stores["a"]["headers"]
    member = _join(api, manager, "member@example.com", "member")
    pid = stores["a"]["product"]["id"]

    assert api.get("/products", headers=member).status_code == 200
    assert api.get(f"/products/{pid}", headers=member).status_code == 200
    assert api.get("/products/catalog", headers=member).status_code == 200

    body = {"name": "New", "category": "Others", "base_unit": "pc"}
    assert api.post("/products", json=body, headers=member).status_code == 403
    assert api.patch(f"/products/{pid}", json={"name": "X"}, headers=member).status_code == 403
    assert api.post(f"/products/{pid}/archive", headers=member).status_code == 403
    assert api.post(f"/products/{pid}/unarchive", headers=member).status_code == 403
    imp = api.post("/products/import", json={"keys": ["hollow-block-4in"]}, headers=member)
    assert imp.status_code == 403


def test_secretary_can_write(api, stores):
    secretary = _join(api, stores["a"]["headers"], "sec@example.com", "secretary")
    created = api.post(
        "/products",
        json={"name": "New", "category": "Others", "base_unit": "pc"},
        headers=secretary,
    )
    assert created.status_code == 201
    pid = created.json()["id"]
    assert (
        api.patch(f"/products/{pid}", json={"price_centavos": 100}, headers=secretary).status_code
        == 200
    )
    assert api.post(f"/products/{pid}/archive", headers=secretary).status_code == 200
    imp = api.post("/products/import", json={"keys": ["hollow-block-4in"]}, headers=secretary)
    assert imp.status_code == 200


def test_unauthenticated_is_401(api, stores):
    pid = stores["a"]["product"]["id"]
    assert api.get("/products").status_code == 401
    assert api.get(f"/products/{pid}").status_code == 401
    assert api.get("/products/catalog").status_code == 401
    assert api.post("/products/import", json={"keys": ["hollow-block-4in"]}).status_code == 401


# ---------- search ----------


@pytest.fixture
def imported(api, manager):
    keys = [
        "portland-cement-40kg",
        "latex-paint-semi-gloss-white",
        "deformed-bar-10mm-x-6m",
        "deformed-bar-12mm-x-6m",
        "ordinary-plywood-1-2in-4x8",
        "marine-plywood-1-2in-4x8",
    ]
    assert api.post("/products/import", json={"keys": keys}, headers=manager).status_code == 200
    return manager


def _names(api, headers, query):
    return [p["name"] for p in api.get(f"/products?{query}", headers=headers).json()["items"]]


def test_search_by_alias(api, imported):
    assert _names(api, imported, "q=bakal 10mm") == ["Deformed Bar 10mm x 6m"]
    # Exact alias first; Marine also matches because "marine plywood 1/2" contains the text.
    assert _names(api, imported, "q=plywood 1/2") == [
        'Ordinary Plywood 1/2" (4x8)',
        'Marine Plywood 1/2" (4x8)',
    ]


def test_search_partial_and_case_insensitive(api, imported):
    assert _names(api, imported, "q=BAKAL") == ["Deformed Bar 10mm x 6m", "Deformed Bar 12mm x 6m"]
    assert _names(api, imported, "q=  Marine   1/2 ") == ['Marine Plywood 1/2" (4x8)']


def test_exact_alias_match_is_listed_first(api, imported):
    # "sem" is inside "Semi-Gloss" too, but it is cement's exact alias.
    names = _names(api, imported, "q=sem")
    assert names[0] == "Portland Cement 40kg"
    assert "Latex Paint Semi-Gloss White" in names


def test_search_with_category_filter(api, imported):
    assert _names(api, imported, "q=1/2&category=Wood") == [
        'Marine Plywood 1/2" (4x8)',
        'Ordinary Plywood 1/2" (4x8)',
    ]
    assert _names(api, imported, "q=bakal&category=Wood") == []


def test_like_wildcards_are_treated_as_text(api, imported):
    assert _names(api, imported, "q=%25") == []  # "%"
    assert _names(api, imported, "q=_") == []


def test_bad_category_is_422(api, imported):
    assert api.get("/products?category=Food", headers=imported).status_code == 422


# ---------- pagination ----------


def test_pagination_20_per_page(api, manager):
    for i in range(45):
        make_product(api, manager, name=f"Item {i:02d}", category="Others", base_unit="pc")

    pages = [api.get(f"/products?page={n}", headers=manager).json() for n in (1, 2, 3, 4)]
    assert [len(p["items"]) for p in pages] == [20, 20, 5, 0]
    assert all(p["total"] == 45 and p["pages"] == 3 and p["page_size"] == 20 for p in pages)

    names = [item["name"] for p in pages for item in p["items"]]
    assert names == [f"Item {i:02d}" for i in range(45)]  # sorted, no gaps, no repeats
    assert api.get("/products?page=0", headers=manager).status_code == 422


def test_pagination_total_respects_filters(api, manager):
    for i in range(25):
        make_product(api, manager, name=f"Nail {i:02d}", category="Nails & Screws", base_unit="kg")
    for i in range(3):
        make_product(api, manager, name=f"Pipe {i}", category="Plumbing", base_unit="pc")
    res = api.get("/products?category=Plumbing", headers=manager).json()
    assert res["total"] == 3 and res["pages"] == 1
    res = api.get("/products?q=nail&page=2", headers=manager).json()
    assert res["total"] == 25 and len(res["items"]) == 5
