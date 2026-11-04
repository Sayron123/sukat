from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.core.db import get_db
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_health_db_ok(client):
    fake_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: fake_db

    res = client.get("/health")

    assert res.status_code == 200
    assert res.json() == {"status": "ok", "db": "ok"}
    fake_db.execute.assert_called_once()


def test_health_db_down(client):
    fake_db = MagicMock()
    fake_db.execute.side_effect = OperationalError("SELECT 1", {}, Exception("db down"))
    app.dependency_overrides[get_db] = lambda: fake_db

    res = client.get("/health")

    assert res.status_code == 503
    assert res.json() == {"status": "ok", "db": "error"}


def test_cors_allows_web_origin(client):
    app.dependency_overrides[get_db] = lambda: MagicMock()

    res = client.get("/health", headers={"Origin": "http://localhost:3000"})

    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"
