from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core import db as core_db
from app.core.config import settings
from app.core.db import get_db
from app.inventory import stock_service
from app.main import DB_BUSY, DB_TIMEOUTS, app
from app.products.models import Product
from tests.conftest import TEST_DATABASE_URL, make_product


def test_connections_get_the_safety_timers(db_engine):
    engine = create_engine(TEST_DATABASE_URL, connect_args=core_db.connect_args())
    names = (
        "TimeZone",
        "statement_timeout",
        "lock_timeout",
        "idle_in_transaction_session_timeout",
    )
    with engine.connect() as conn:
        shown = {name: conn.scalar(text(f"SHOW {name}")) for name in names}
    engine.dispose()
    assert shown == {
        "TimeZone": "UTC",
        "statement_timeout": "30s",
        "lock_timeout": "10s",
        "idle_in_transaction_session_timeout": "1min",
    }


def test_a_query_past_the_statement_timeout_is_cancelled(db_engine, monkeypatch):
    monkeypatch.setattr(settings, "DB_STATEMENT_TIMEOUT_MS", 100)
    engine = create_engine(TEST_DATABASE_URL, connect_args=core_db.connect_args())
    try:
        with engine.connect() as conn, pytest.raises(OperationalError) as caught:
            conn.execute(text("SELECT pg_sleep(1)"))
    finally:
        engine.dispose()
    assert isinstance(caught.value.orig, DB_TIMEOUTS)


def test_a_save_waiting_on_a_stuck_lock_answers_busy_and_can_be_repeated(
    api, db, manager, monkeypatch
):
    cement = make_product(api, manager)
    monkeypatch.setattr(settings, "DB_LOCK_TIMEOUT_MS", 200)
    engine = create_engine(TEST_DATABASE_URL, connect_args=core_db.connect_args())
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        with sessions() as session:
            yield session

    app.dependency_overrides[get_db] = _get_db
    body = {
        "client_request_id": "stuck-lock-1",
        "type": "stock_in",
        "lines": [{"product_id": cement["id"], "qty": "2", "unit": "bag"}],
    }
    try:
        db.execute(select(Product).where(Product.id == cement["id"]).with_for_update())
        blocked = api.post("/transactions", json=body, headers=manager)
        db.rollback()
        repeated = api.post("/transactions", json=body, headers=manager)
    finally:
        engine.dispose()

    assert blocked.status_code == 503
    assert blocked.json() == {"detail": DB_BUSY}
    assert blocked.headers["Retry-After"] == "5"
    assert repeated.status_code == 201
    assert repeated.json()["items"][0]["stock_after"] == "2.000"


def test_other_database_errors_are_not_reported_as_busy(api, manager, monkeypatch):
    def broken(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("connection lost"))

    monkeypatch.setattr(stock_service, "save_transaction_once", broken)
    body = {
        "client_request_id": "db-error-1",
        "type": "stock_in",
        "lines": [{"product_id": str(uuid4()), "qty": "1", "unit": "bag"}],
    }
    with pytest.raises(OperationalError):
        api.post("/transactions", json=body, headers=manager)
