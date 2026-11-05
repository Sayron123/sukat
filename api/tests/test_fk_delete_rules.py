"""Foreign key delete rules: history can't be deleted out from under a store or user."""

import os
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import Connection, Engine, delete, func, select, text
from sqlalchemy.exc import IntegrityError

from alembic import command
from app.auth.models import User
from app.core.base import Base
from app.inventory.models import StockMovement, Transaction, TransactionItem
from app.stores.models import Store
from tests.conftest import TEST_DATABASE_URL, make_product

TABLES_WITH_STORE_ID = [
    "ai_usage",
    "invites",
    "product_aliases",
    "products",
    "scans",
    "stock_movements",
    "store_members",
    "transaction_items",
    "transactions",
    "unit_conversions",
]

RESTRICT = "r"
EXPECTED_RULES = {
    **{f"fk_{table}_store_id_stores": RESTRICT for table in TABLES_WITH_STORE_ID},
    "fk_transaction_items_transaction_id_transactions": RESTRICT,
    "fk_stock_movements_transaction_item_id_transaction_items": RESTRICT,
    "fk_transactions_created_by_users": RESTRICT,
    "fk_transactions_voided_by_users": RESTRICT,
    "fk_scans_created_by_users": RESTRICT,
    "fk_stock_movements_created_by_users": RESTRICT,
    "fk_store_members_user_id_users": RESTRICT,
    # Deliberately not RESTRICT:
    "fk_product_aliases_product_id_products": "c",  # CASCADE
    "fk_unit_conversions_product_id_products": "c",  # CASCADE
    "fk_invites_invited_by_user_id_users": "n",  # SET NULL
}


def _delete_rules(conn: Connection) -> dict[str, str]:
    """{constraint name: rule} from Postgres. Rules: r=RESTRICT, c=CASCADE, n=SET NULL."""
    rows = conn.execute(
        text("SELECT conname, confdeltype FROM pg_constraint WHERE contype = 'f'")
    ).all()
    return {name: rule for name, rule in rows}


def _is_nullable(conn: Connection, table: str, column: str) -> bool:
    return (
        conn.scalar(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
            ),
            {"t": table, "c": column},
        )
        == "YES"
    )


def _constraint_name(exc: IntegrityError) -> str:
    return exc.orig.diag.constraint_name  # type: ignore[union-attr]


def _alembic_config() -> Config:
    here = os.path.dirname(__file__)
    cfg = Config(os.path.join(here, "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(here, "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    return cfg


def _sale(api, headers) -> dict:
    """Stock in a product, then sell it. Returns the sale."""
    product = make_product(api, headers, price_centavos=25000)
    for txn_type, qty in (("stock_in", "10"), ("sale", "2")):
        res = api.post(
            "/transactions",
            json={
                "client_request_id": uuid.uuid4().hex,
                "type": txn_type,
                "lines": [{"product_id": product["id"], "qty": qty, "unit": "bag"}],
            },
            headers=headers,
        )
        assert res.status_code == 201, res.text
    return res.json()


def test_database_has_the_expected_delete_rules(db):
    rules = _delete_rules(db.connection())
    assert {name: rules.get(name) for name in EXPECTED_RULES} == EXPECTED_RULES


def test_models_match_the_expected_delete_rules():
    model_rules = {
        fk.name: fk.ondelete
        for table in Base.metadata.tables.values()
        for fk in table.foreign_key_constraints
    }
    words = {"r": "RESTRICT", "c": "CASCADE", "n": "SET NULL"}
    expected = {name: words[rule] for name, rule in EXPECTED_RULES.items()}
    assert {name: model_rules.get(name) for name in expected} == expected


def test_created_by_is_not_null(db):
    for table in ("scans", "stock_movements", "transactions"):
        assert not _is_nullable(db.connection(), table, "created_by"), table


def test_deleting_a_store_with_data_fails(api, db, manager):
    _sale(api, manager)
    store_id = db.scalar(select(Store.id))

    with pytest.raises(IntegrityError) as caught:
        db.execute(delete(Store).where(Store.id == store_id))
    db.rollback()

    assert _constraint_name(caught.value).endswith("_store_id_stores")
    assert db.get(Store, store_id) is not None
    assert db.scalar(select(func.count()).select_from(Transaction)) == 2


def test_deleting_a_transaction_with_items_fails(api, db, manager):
    sale = _sale(api, manager)
    sale_id = uuid.UUID(sale["id"])
    # Movements also point at the transaction, so remove them to test the item rule alone.
    db.execute(delete(StockMovement).where(StockMovement.transaction_id == sale_id))
    db.commit()

    with pytest.raises(IntegrityError) as caught:
        db.execute(delete(Transaction).where(Transaction.id == sale_id))
    db.rollback()

    assert _constraint_name(caught.value) == "fk_transaction_items_transaction_id_transactions"
    count = select(func.count()).select_from(TransactionItem)
    assert db.scalar(count.where(TransactionItem.transaction_id == sale_id)) == 1


def test_orm_delete_of_a_transaction_with_items_also_fails(api, db, manager):
    """The relationship must not delete or un-parent the lines before Postgres can refuse."""
    sale_id = uuid.UUID(_sale(api, manager)["id"])
    db.execute(delete(StockMovement).where(StockMovement.transaction_id == sale_id))
    db.commit()
    txn = db.get(Transaction, sale_id)
    assert txn is not None and len(txn.items) == 1

    db.delete(txn)
    with pytest.raises(IntegrityError) as caught:
        db.commit()
    db.rollback()

    assert _constraint_name(caught.value) == "fk_transaction_items_transaction_id_transactions"
    assert db.get(Transaction, sale_id) is not None


def test_deleting_a_line_with_a_stock_movement_fails(api, db, manager):
    sale_id = uuid.UUID(_sale(api, manager)["id"])
    item_id = db.scalar(select(TransactionItem.id).where(TransactionItem.transaction_id == sale_id))

    with pytest.raises(IntegrityError) as caught:
        db.execute(delete(TransactionItem).where(TransactionItem.id == item_id))
    db.rollback()

    assert (
        _constraint_name(caught.value) == "fk_stock_movements_transaction_item_id_transaction_items"
    )


def test_deleting_a_user_who_created_a_transaction_fails(api, db, manager):
    """This user has no membership, scans, or movements, so only created_by can block it."""
    _sale(api, manager)
    store_id = db.scalar(select(Store.id))
    former = User(email="former@example.com", password_hash="x", full_name="Former Staff")
    db.add(former)
    db.flush()
    db.add(
        Transaction(
            store_id=store_id,
            type="sale",
            client_request_id=uuid.uuid4().hex,
            created_by=former.id,
        )
    )
    db.commit()

    with pytest.raises(IntegrityError) as caught:
        db.execute(delete(User).where(User.id == former.id))
    db.rollback()

    assert _constraint_name(caught.value) == "fk_transactions_created_by_users"
    assert db.get(User, former.id) is not None


def test_deleting_a_user_with_a_membership_fails(api, db, manager):
    user_id = db.scalar(select(User.id))
    # A brand-new store has no history, so only the membership can block this delete.
    with pytest.raises(IntegrityError) as caught:
        db.execute(delete(User).where(User.id == user_id))
    db.rollback()

    assert _constraint_name(caught.value) == "fk_store_members_user_id_users"


def test_product_delete_still_cascades_to_aliases_and_conversions(api, db, manager):
    product = make_product(
        api,
        manager,
        aliases=["sem"],
        conversions=[{"from_unit": "pallet", "factor": "40"}],
    )
    db.execute(
        text("DELETE FROM products WHERE id = :id"),
        {"id": uuid.UUID(product["id"])},
    )
    db.commit()

    assert db.scalar(text("SELECT count(*) FROM product_aliases")) == 0
    assert db.scalar(text("SELECT count(*) FROM unit_conversions")) == 0


def test_deleting_the_inviter_still_clears_invited_by(api, db, manager):
    invite = api.post(
        "/staff/invites", json={"email": "new@example.com", "role": "member"}, headers=manager
    )
    assert invite.status_code == 201, invite.text
    store_id = db.scalar(select(Store.id))
    inviter = User(email="inviter@example.com", password_hash="x", full_name="Inviter")
    db.add(inviter)
    db.flush()
    db.execute(
        text("UPDATE invites SET invited_by_user_id = :u WHERE store_id = :s"),
        {"u": inviter.id, "s": store_id},
    )
    db.commit()

    db.execute(delete(User).where(User.id == inviter.id))
    db.commit()

    assert db.scalar(text("SELECT invited_by_user_id FROM invites")) is None


@pytest.fixture
def at_previous_revision(db_engine: Engine):
    """Run a test one migration back. Always returns the database to head afterwards."""
    cfg = _alembic_config()
    command.downgrade(cfg, "0007")
    try:
        yield cfg
    finally:
        with db_engine.begin() as conn:
            conn.execute(text("TRUNCATE scans, stores CASCADE"))
        # Back to 0007 first, so a test that stopped at a mixed state still ends at clean head.
        command.downgrade(cfg, "0007")
        command.upgrade(cfg, "head")


def test_downgrade_restores_the_old_rules_and_upgrade_reapplies(db_engine, at_previous_revision):
    with db_engine.connect() as conn:
        rules = _delete_rules(conn)
        for table in TABLES_WITH_STORE_ID:
            assert rules[f"fk_{table}_store_id_stores"] == "c", table
        assert rules["fk_transaction_items_transaction_id_transactions"] == "c"
        assert rules["fk_stock_movements_transaction_item_id_transaction_items"] == "c"
        assert rules["fk_store_members_user_id_users"] == "c"
        for name in (
            "fk_transactions_created_by_users",
            "fk_transactions_voided_by_users",
            "fk_scans_created_by_users",
            "fk_stock_movements_created_by_users",
        ):
            assert rules[name] == "n", name
        for table in ("scans", "stock_movements", "transactions"):
            assert _is_nullable(conn, table, "created_by"), table

    command.upgrade(at_previous_revision, "head")
    with db_engine.connect() as conn:
        rules = _delete_rules(conn)
    assert {name: rules.get(name) for name in EXPECTED_RULES} == EXPECTED_RULES


def test_upgrade_keeps_created_by_nullable_only_where_nulls_exist(db_engine, at_previous_revision):
    store_id = uuid.uuid4()
    with db_engine.begin() as conn:
        conn.execute(text("INSERT INTO stores (id, name) VALUES (:id, 'S')"), {"id": store_id})
        conn.execute(
            text(
                "INSERT INTO scans (store_id, type, photo_key, created_by) "
                "VALUES (:id, 'sale', 'k', NULL)"
            ),
            {"id": store_id},
        )

    command.upgrade(at_previous_revision, "head")

    with db_engine.connect() as conn:
        assert _is_nullable(conn, "scans", "created_by")
        assert not _is_nullable(conn, "transactions", "created_by")
        assert not _is_nullable(conn, "stock_movements", "created_by")
        assert _delete_rules(conn)["fk_scans_created_by_users"] == RESTRICT

    # Downgrade must also work from this mixed state.
    command.downgrade(at_previous_revision, "0007")
    with db_engine.connect() as conn:
        assert _is_nullable(conn, "transactions", "created_by")
