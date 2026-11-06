import uuid

from sqlalchemy import select, update

from app.products.catalog import load_catalog
from app.products.models import Product
from tests.conftest import make_product


def test_create_and_get_product(api, manager):
    p = make_product(
        api,
        manager,
        name='  Common Wire Nail   4" ',
        category="Nails & Screws",
        base_unit=" KG ",
        price_centavos=8500,
        low_stock_level="10",
        aliases=["Pako 4", "  CWN   4 "],
        conversions=[{"from_unit": "Box", "factor": "25"}],
    )
    assert p["name"] == 'Common Wire Nail 4"'
    assert p["base_unit"] == "kg"
    assert p["aliases"] == ["cwn 4", "pako 4"]  # cleaned, lowercased, sorted
    assert p["conversions"] == [{"from_unit": "box", "factor": "25.000000"}]
    assert p["stock_qty"] == "0.000"
    assert p["is_low_stock"] is True  # 0 <= 10
    assert api.get(f"/products/{p['id']}", headers=manager).json() == p


def test_stock_qty_cannot_be_set_through_the_product_api(api, manager):
    res = api.post(
        "/products",
        json={"name": "X", "category": "Others", "base_unit": "pc", "stock_qty": "99"},
        headers=manager,
    )
    assert res.status_code == 422
    p = make_product(api, manager)
    res = api.patch(f"/products/{p['id']}", json={"stock_qty": "99"}, headers=manager)
    assert res.status_code == 422
    assert api.get(f"/products/{p['id']}", headers=manager).json()["stock_qty"] == "0.000"


def test_duplicate_name_or_alias_is_409(api, manager):
    make_product(api, manager, aliases=["sem"])
    dup_name = api.post(
        "/products",
        json={"name": "PORTLAND CEMENT 40KG", "category": "Cement", "base_unit": "bag"},
        headers=manager,
    )
    assert dup_name.status_code == 409
    dup_alias = api.post(
        "/products",
        json={"name": "Other", "category": "Cement", "base_unit": "bag", "aliases": ["SEM"]},
        headers=manager,
    )
    assert dup_alias.status_code == 409
    assert "sem" in dup_alias.json()["detail"]


def test_invalid_input_is_422(api, manager):
    bad = [
        {"name": " ", "category": "Cement", "base_unit": "bag"},
        {"name": "A", "category": "Food", "base_unit": "bag"},
        {"name": "A", "category": "Cement", "base_unit": "bag", "price_centavos": -1},
        {"name": "A", "category": "Cement", "base_unit": "bag", "low_stock_level": "1.2345"},
        {"name": "A", "category": "Cement", "base_unit": "bag", "aliases": ["x", "X"]},
        {
            "name": "A",
            "category": "Cement",
            "base_unit": "bag",
            "conversions": [{"from_unit": "bag", "factor": "2"}],
        },
        {
            "name": "A",
            "category": "Cement",
            "base_unit": "bag",
            "conversions": [{"from_unit": "kg", "factor": "0"}],
        },
    ]
    for body in bad:
        assert api.post("/products", json=body, headers=manager).status_code == 422, body


def test_update_product(api, manager):
    p = make_product(
        api,
        manager,
        price_centavos=25000,
        aliases=["sem", "semento"],
        conversions=[{"from_unit": "kg", "factor": "0.025"}],
    )
    res = api.patch(
        f"/products/{p['id']}",
        json={
            "price_centavos": None,  # clear the price
            "aliases": ["semento", "simento"],  # keep one, drop one, add one
            "conversions": [{"from_unit": "kg", "factor": "0.04"}],  # change factor
        },
        headers=manager,
    )
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["price_centavos"] is None
    assert out["name"] == p["name"]  # untouched
    assert out["aliases"] == ["semento", "simento"]
    assert out["conversions"] == [{"from_unit": "kg", "factor": "0.040000"}]


def test_update_rejects_null_required_fields_and_base_unit_clash(api, manager):
    p = make_product(api, manager, conversions=[{"from_unit": "kg", "factor": "0.025"}])
    assert (
        api.patch(f"/products/{p['id']}", json={"name": None}, headers=manager).status_code == 422
    )
    clash = api.patch(f"/products/{p['id']}", json={"base_unit": "kg"}, headers=manager)
    assert clash.status_code == 422


def test_rename_to_own_name_with_different_case_is_ok(api, manager):
    p = make_product(api, manager)
    res = api.patch(f"/products/{p['id']}", json={"name": "PORTLAND cement 40kg"}, headers=manager)
    assert res.status_code == 200


def test_archive_hides_from_list_and_unarchive_restores(api, manager):
    p = make_product(api, manager)
    assert api.post(f"/products/{p['id']}/archive", headers=manager).json()["archived"] is True
    assert api.get("/products", headers=manager).json()["total"] == 0
    archived = api.get("/products?include_archived=true", headers=manager).json()
    assert archived["total"] == 1
    assert api.post(f"/products/{p['id']}/unarchive", headers=manager).json()["archived"] is False
    assert api.get("/products", headers=manager).json()["total"] == 1


def test_low_stock_filter(api, db, manager):
    low = make_product(api, manager, name="Low", low_stock_level="5")
    make_product(api, manager, name="No level")
    ok = make_product(api, manager, name="Plenty", low_stock_level="5")
    db.execute(update(Product).where(Product.id == ok["id"]).values(stock_qty=50))
    db.commit()
    res = api.get("/products?low_stock=true", headers=manager).json()
    assert [p["id"] for p in res["items"]] == [low["id"]]


def test_catalog_lists_items_and_marks_imported(api, manager):
    catalog = api.get("/products/catalog", headers=manager).json()
    assert len(catalog) == len(load_catalog().items)
    assert not any(i["already_in_store"] for i in catalog)

    api.post("/products/import", json={"keys": ["portland-cement-40kg"]}, headers=manager)
    marked = {
        i["key"]
        for i in api.get("/products/catalog", headers=manager).json()
        if i["already_in_store"]
    }
    assert marked == {"portland-cement-40kg"}


def test_import_creates_products_with_aliases_and_conversions(api, db, manager):
    keys = ["portland-cement-40kg", "deformed-bar-10mm-x-6m", "common-wire-nail-4in"]
    res = api.post("/products/import", json={"keys": keys}, headers=manager)
    assert res.status_code == 200, res.text
    assert res.json() == {"created": 3, "skipped": [], "dropped_aliases": []}

    nails = api.get("/products?q=pako 4", headers=manager).json()["items"][0]
    assert nails["name"] == 'Common Wire Nail 4"'
    assert nails["conversions"] == [{"from_unit": "box", "factor": "25.000000"}]
    assert nails["price_centavos"] is None and nails["stock_qty"] == "0.000"


def test_import_is_safe_to_repeat_and_drops_clashing_aliases(api, manager):
    make_product(api, manager, name="My Cement", aliases=["sem"])
    first = api.post("/products/import", json={"keys": ["portland-cement-40kg"]}, headers=manager)
    assert first.json()["created"] == 1
    assert first.json()["dropped_aliases"] == [
        {"key": "portland-cement-40kg", "alias": "sem", "reason": "used by another product"}
    ]
    again = api.post(
        "/products/import",
        json={"keys": ["portland-cement-40kg", "portland-cement-40kg"]},
        headers=manager,
    )
    assert again.json()["created"] == 0
    assert [s["reason"] for s in again.json()["skipped"]] == ["already in store"]


def test_import_unknown_key_is_422_and_creates_nothing(api, db, manager):
    res = api.post(
        "/products/import", json={"keys": ["portland-cement-40kg", "nope"]}, headers=manager
    )
    assert res.status_code == 422
    assert "nope" in res.json()["detail"]
    assert db.scalar(select(Product)) is None


def test_import_everything(api, manager):
    keys = [i.key for i in load_catalog().items]
    res = api.post("/products/import", json={"keys": keys}, headers=manager)
    assert res.status_code == 200, res.text
    assert res.json()["created"] == len(keys)
    assert res.json()["dropped_aliases"] == []


def test_units_are_saved_in_canonical_spelling(api, manager):
    p = make_product(
        api,
        manager,
        name="Nails",
        base_unit="Kilos",
        conversions=[{"from_unit": "Kahon", "factor": "25"}],
    )
    assert p["base_unit"] == "kg"
    assert p["conversions"][0]["from_unit"] == "box"
    clash = api.post(
        "/products",
        json={
            "name": "Y",
            "category": "Others",
            "base_unit": "pcs",
            "conversions": [{"from_unit": "piece", "factor": "2"}],
        },
        headers=manager,
    )
    assert clash.status_code == 422  # "piece" is the base unit "pc"


# ---------- review fixes ----------


def test_base_unit_cannot_change_while_there_is_stock(api, db, manager):
    p = make_product(api, manager, name="Nails", base_unit="kg")
    db.execute(update(Product).where(Product.id == p["id"]).values(stock_qty=50))
    db.commit()
    res = api.patch(f"/products/{p['id']}", json={"base_unit": "g"}, headers=manager)
    assert res.status_code == 409
    assert "Archive this product" in res.json()["detail"]
    assert api.get(f"/products/{p['id']}", headers=manager).json()["base_unit"] == "kg"


def test_base_unit_change_must_restate_conversions(api, manager):
    p = make_product(
        api,
        manager,
        name="Nails",
        base_unit="kg",
        conversions=[{"from_unit": "box", "factor": "25"}],
    )
    assert (
        api.patch(f"/products/{p['id']}", json={"base_unit": "g"}, headers=manager).status_code
        == 422
    )
    ok = api.patch(
        f"/products/{p['id']}",
        json={"base_unit": "g", "conversions": [{"from_unit": "box", "factor": "25000"}]},
        headers=manager,
    )
    assert ok.status_code == 200
    assert ok.json()["conversions"] == [{"from_unit": "box", "factor": "25000.000000"}]


def test_same_base_unit_in_patch_is_not_a_change(api, manager):
    p = make_product(api, manager, conversions=[{"from_unit": "kg", "factor": "0.025"}])
    res = api.patch(
        f"/products/{p['id']}", json={"base_unit": "Bag", "name": "Cement"}, headers=manager
    )
    assert res.status_code == 200


def test_huge_page_number_is_422_not_500(api, manager):
    assert api.get("/products?page=10001", headers=manager).status_code == 422
    assert api.get("/products?page=10000000000000000000", headers=manager).status_code == 422


def test_price_limit(api, manager):
    ok = make_product(api, manager, name="Big", price_centavos=999_999_999)
    assert ok["price_centavos"] == 999_999_999
    too_big = api.post(
        "/products",
        json={"name": "Bigger", "category": "Others", "base_unit": "pc", "price_centavos": 10**9},
        headers=manager,
    )
    assert too_big.status_code == 422


def test_archived_name_clash_says_archived(api, manager):
    p = make_product(api, manager)
    api.post(f"/products/{p['id']}/archive", headers=manager)
    res = api.post(
        "/products",
        json={"name": "Portland Cement 40kg", "category": "Cement", "base_unit": "bag"},
        headers=manager,
    )
    assert res.status_code == 409 and "archived" in res.json()["detail"]
    imp = api.post("/products/import", json={"keys": ["portland-cement-40kg"]}, headers=manager)
    assert imp.json()["skipped"][0]["reason"] == "archived in store"


# ---------- phase 5 audit fixes ----------


def _move(api, headers, txn_type, product_id, qty, unit):
    body = {
        "client_request_id": uuid.uuid4().hex,
        "type": txn_type,
        "lines": [{"product_id": product_id, "qty": qty, "unit": unit}],
    }
    res = api.post("/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text


def test_base_unit_cannot_change_after_stock_has_moved(api, manager):
    """Movements don't store a unit, so a later unit change would relabel old history
    ("+10 roll" shown as "+10 m") and mix both units in best sellers."""
    p = make_product(api, manager, name="Electrical Wire", category="Electrical", base_unit="roll")
    _move(api, manager, "stock_in", p["id"], "10", "roll")
    _move(api, manager, "sale", p["id"], "10", "roll")  # back to 0 stock
    res = api.patch(f"/products/{p['id']}", json={"base_unit": "m"}, headers=manager)
    assert res.status_code == 409
    assert "after stock has moved" in res.json()["detail"]
    assert api.get(f"/products/{p['id']}", headers=manager).json()["base_unit"] == "roll"


def test_base_unit_can_change_before_any_movement(api, manager):
    p = make_product(api, manager, name="Electrical Wire", category="Electrical", base_unit="roll")
    res = api.patch(f"/products/{p['id']}", json={"base_unit": "m"}, headers=manager)
    assert res.status_code == 200 and res.json()["base_unit"] == "m"


def test_base_unit_change_with_stock_gives_the_archive_advice(api, manager):
    """With stock on hand, "bring stock to 0 first" was a dead end: getting to 0 needs a
    movement, and any movement blocks the change. The answer is the same either way."""
    p = make_product(api, manager, name="Electrical Wire", category="Electrical", base_unit="roll")
    _move(api, manager, "stock_in", p["id"], "10", "roll")
    res = api.patch(f"/products/{p['id']}", json={"base_unit": "m"}, headers=manager)
    assert res.status_code == 409
    assert "Archive this product" in res.json()["detail"]
    assert "Bring stock to 0" not in res.json()["detail"]


def test_base_unit_change_waits_for_a_stock_save_in_progress(api, manager, db_sessionmaker):
    """A sale or stock-in that holds the product's lock must finish first, so its
    movement is seen and the change is refused (not saved over the new movement)."""
    import threading

    from app.inventory.models import StockMovement
    from app.products.models import Product as ProductRow
    from app.products.schemas import ProductUpdate
    from app.products.service import update_product

    wire = make_product(
        api, manager, name="Electrical Wire", category="Electrical", base_unit="roll"
    )
    other = make_product(api, manager, name="Nylon Rope", category="Others", base_unit="m")
    _move(api, manager, "stock_in", other["id"], "1", "m")  # a transaction to point at
    me = api.get("/auth/me", headers=manager).json()
    store_id, wire_id = uuid.UUID(me["store_id"]), uuid.UUID(wire["id"])

    with db_sessionmaker() as saver:
        # Like stock_service: lock the product, then write a movement (not committed yet).
        saver.scalar(select(ProductRow).where(ProductRow.id == wire_id).with_for_update())
        txn_id = saver.scalar(select(StockMovement.transaction_id))
        saver.add(
            StockMovement(
                store_id=store_id,
                product_id=wire_id,
                transaction_id=txn_id,
                qty_change=1,
                stock_after=1,
                created_by=uuid.UUID(me["user_id"]),
            )
        )
        saver.flush()

        outcome: list[object] = []

        def change_unit() -> None:
            with db_sessionmaker() as s:
                try:
                    update_product(s, store_id, wire_id, ProductUpdate(base_unit="m"))
                    outcome.append("changed")
                except Exception as e:  # noqa: BLE001 - the test inspects it below
                    outcome.append(e)

        worker = threading.Thread(target=change_unit)
        worker.start()
        worker.join(timeout=1)
        saver.commit()  # the save finishes; only now may the unit change continue
        worker.join(timeout=10)

    assert not worker.is_alive()
    assert len(outcome) == 1 and type(outcome[0]).__name__ == "Conflict", outcome
    assert api.get(f"/products/{wire['id']}", headers=manager).json()["base_unit"] == "roll"
