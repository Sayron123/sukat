"""Test setup for tests that need a real Postgres database.

Uses TEST_DATABASE_URL (default: a 'sukat_test' database on the local Postgres).
The database is created if missing, migrated with Alembic, and wiped between tests.
"""

import os

# Settings default to production, which refuses the public dev JWT secret. Tests run as
# development, so they work without a .env file. Must be set before `app` is imported.
os.environ["APP_ENV"] = "development"
os.environ["EMAIL_BACKEND"] = "smtp"
os.environ["EMAIL_WORKER_ENABLED"] = "false"
os.environ["SMTP_HOST"] = "smtp.test"
os.environ["SMTP_FROM"] = "sukat@example.com"
os.environ["AI_PROVIDER"] = "gemini"
os.environ["AI_FALLBACK_PROVIDER"] = "none"
os.environ["AI_MONTHLY_BUDGET_CENTAVOS"] = "50000"

from collections.abc import Callable, Generator  # noqa: E402
from datetime import UTC, datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import Engine, create_engine, make_url, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from alembic import command  # noqa: E402
from app.core.db import get_db  # noqa: E402
from app.core.mailer import Email  # noqa: E402
from app.core.outbox import deliver_due_emails  # noqa: E402
from app.core.storage import LocalStorage, get_storage  # noqa: E402
from app.main import app  # noqa: E402

# Shared fixtures that live in their own module (e.g. the scripted chat model).
pytest_plugins = ["tests.chat_helpers"]

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://sukat:sukat@localhost:5432/sukat_test"
)
API_BASE_URL = "http://testserver/v1"

TABLES = [
    "stock_movements",
    "transaction_items",
    "transactions",
    "scans",
    "ai_usage",
    "unit_conversions",
    "product_aliases",
    "products",
    "auth_failures",
    "auth_tokens",
    "email_outbox",
    "invites",
    "store_members",
    "users",
    "stores",
]


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


@pytest.fixture(autouse=True)
def fresh_ai_providers() -> Generator[None]:
    from app.ai import provider

    cached = (provider.get_scan_ai, provider.get_backup_scan_ai)
    for f in cached:
        f.cache_clear()
    yield
    for f in cached:
        f.cache_clear()


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
def storage(tmp_path) -> LocalStorage:
    """Photo storage in a temp folder, so tests never touch real files or R2."""
    return LocalStorage(str(tmp_path / "uploads"), "http://testserver", "test-secret")


class FakeMailer:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self.sessions = sessions
        self.delivered: list[Email] = []

    def send(self, email: Email) -> None:
        self.delivered.append(email)

    @property
    def sent(self) -> list[Email]:
        with self.sessions() as session:
            deliver_due_emails(session, self, datetime.now(UTC) + timedelta(seconds=1))
        return self.delivered


@pytest.fixture
def mailer(db_sessionmaker: sessionmaker[Session]) -> FakeMailer:
    return FakeMailer(db_sessionmaker)


@pytest.fixture
def api(db_sessionmaker: sessionmaker[Session], storage: LocalStorage) -> Generator[TestClient]:
    """A test client whose requests use the test database and temp storage."""

    def _get_test_db() -> Generator[Session]:
        with db_sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_storage] = lambda: storage
    # Relative paths like "/auth/signup" go to /v1/auth/signup, like the real clients.
    with TestClient(app, base_url=API_BASE_URL) as client:
        yield client
    app.dependency_overrides.clear()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def signup(
    api: TestClient, db_sessionmaker: sessionmaker[Session]
) -> Callable[..., dict[str, Any]]:
    """Sign up a new store + manager. Returns the JSON response plus the email used."""

    def _signup(
        email: str = "owner@example.com",
        store_name: str = "Store A",
        password: str = "Correct-horse-1",
        full_name: str = "Owner",
    ) -> dict[str, Any]:
        res = api.post(
            "/auth/signup",
            json={
                "store_name": store_name,
                "full_name": full_name,
                "email": email,
                "password": password,
                "accept_terms": True,
            },
        )
        assert res.status_code == 201, res.text
        with db_sessionmaker() as session:
            session.execute(
                text("UPDATE users SET email_verified_at = now() WHERE email = :e"), {"e": email}
            )
            session.commit()
        return {**res.json(), "email": email, "password": password}

    return _signup


@pytest.fixture
def manager(signup) -> dict[str, str]:
    """Auth header for a fresh store's manager."""
    return auth_header(signup()["access_token"])


def make_product(api: TestClient, headers: dict[str, str], **overrides: Any) -> dict[str, Any]:
    body = {"name": "Portland Cement 40kg", "category": "Cement", "base_unit": "bag"}
    body.update(overrides)
    res = api.post("/products", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ---------- scans: fake AI + photo helpers ----------

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 60


class FakeReader:
    """Stands in for the AI. Set `.lines` (list of ScanLine or a callable taking the
    catalog) or `.error` (an AIReadError); every call is recorded."""

    def __init__(self, provider: str = "gemini", model: str = "fake-model") -> None:
        self.model = model
        self.provider = provider
        self.lines: Any = [scan_line()]
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    def read_list(self, image, media_type, catalog, scan_type):
        from app.ai.schemas import AIUsageInfo, ReadResult

        self.calls.append(
            {"image": image, "media_type": media_type, "catalog": catalog, "type": scan_type}
        )
        if self.error is not None:
            raise self.error
        lines = self.lines(catalog) if callable(self.lines) else self.lines
        usage = AIUsageInfo(
            model=self.model,
            provider=self.provider,
            input_tokens=1000,
            output_tokens=200,
        )
        return ReadResult(lines=lines, usage=usage, raw={"lines": "fake"})


@pytest.fixture
def reader(api) -> Generator[FakeReader]:
    from app.ai.provider import get_vision_reader

    fake = FakeReader()
    app.dependency_overrides[get_vision_reader] = lambda: fake
    yield fake


def upload_photo(
    api: TestClient, headers: dict[str, str], storage: LocalStorage, data: bytes = JPEG_BYTES
) -> str:
    """Get an upload URL and store the photo directly (skips the HTTP PUT). Returns key."""
    res = api.post("/scans/upload-url", json={"size_bytes": len(data)}, headers=headers)
    assert res.status_code == 200, res.text
    key = res.json()["photo_key"]
    storage.save(key, data)
    return key


def scan_line(product_id=None, **kw: Any):
    from decimal import Decimal

    from app.ai.schemas import ScanLine

    values: dict[str, Any] = {
        "raw_text": "line",
        "product_id": product_id,
        "suggested_new_name": None,
        "qty": Decimal("1"),
        "unit": "pc",
        "unit_price_centavos": None,
        "confidence": 0.95,
    }
    values.update(kw)
    return ScanLine(**values)
