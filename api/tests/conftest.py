"""Test setup for tests that need a real Postgres database.

Uses TEST_DATABASE_URL (default: a 'sukat_test' database on the local Postgres).
The database is created if missing, migrated with Alembic, and wiped between tests.
"""

import os
from collections.abc import Callable, Generator
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, make_url, text
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.db import get_db
from app.main import app

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://sukat:sukat@localhost:5432/sukat_test"
)
TABLES = ["invites", "store_members", "users", "stores"]


def _create_database_if_missing(url: str) -> None:
    db_url = make_url(url)
    admin = create_engine(db_url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": db_url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{db_url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def db_engine() -> Generator[Engine]:
    _create_database_if_missing(TEST_DATABASE_URL)
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL.replace("%", "%%"))
    command.upgrade(cfg, "head")
    engine = create_engine(TEST_DATABASE_URL, connect_args={"options": "-c timezone=UTC"})
    yield engine
    engine.dispose()


@pytest.fixture
def db_sessionmaker(db_engine: Engine) -> Generator[sessionmaker[Session]]:
    with db_engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
    yield sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(db_sessionmaker: sessionmaker[Session]) -> Generator[Session]:
    """A session for arranging/inspecting data directly in a test."""
    with db_sessionmaker() as session:
        yield session


@pytest.fixture
def api(db_sessionmaker: sessionmaker[Session]) -> Generator[TestClient]:
    """A test client whose requests use the test database."""

    def _get_test_db() -> Generator[Session]:
        with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def signup(api: TestClient) -> Callable[..., dict[str, Any]]:
    """Sign up a new store + manager. Returns the JSON response plus the email used."""

    def _signup(
        email: str = "owner@example.com",
        store_name: str = "Store A",
        password: str = "correct-horse-1",
        full_name: str = "Owner",
    ) -> dict[str, Any]:
        res = api.post(
            "/auth/signup",
            json={
                "store_name": store_name,
                "full_name": full_name,
                "email": email,
                "password": password,
            },
        )
        assert res.status_code == 201, res.text
        return {**res.json(), "email": email, "password": password}

    return _signup
