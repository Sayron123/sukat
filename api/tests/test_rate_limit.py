from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.auth.models import AuthFailure
from app.core.config import settings
from tests.conftest import auth_header


@pytest.fixture(autouse=True)
def small_limits(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MAX_FAILURES_PER_EMAIL", 3)
    monkeypatch.setattr(settings, "AUTH_MAX_FAILURES_PER_IP", 5)


def _login(api, email="owner@example.com", password="wrong-pass"):
    return api.post("/auth/login", json={"email": email, "password": password})


def test_too_many_wrong_passwords_blocks_even_the_right_one(api, signup):
    out = signup()
    for _ in range(3):
        assert _login(api).status_code == 401
    blocked = _login(api, password=out["password"])
    assert blocked.status_code == 429
    assert int(blocked.headers["Retry-After"]) > 0


def test_unknown_email_is_limited_the_same_way(api):
    for _ in range(3):
        assert _login(api, email="ghost@example.com").status_code == 401
    assert _login(api, email="ghost@example.com").status_code == 429


def test_success_resets_the_email_counter(api, signup):
    out = signup()
    for _ in range(2):
        _login(api)
    assert _login(api, password=out["password"]).status_code == 200
    for _ in range(2):
        assert _login(api).status_code == 401  # would be 429 if the counter was not reset


def test_one_email_being_attacked_does_not_block_another(api, signup):
    signup(email="a@example.com", store_name="A")
    signup(email="b@example.com", store_name="B", password="b-password-1")
    for _ in range(3):
        _login(api, email="a@example.com")
    assert _login(api, email="a@example.com").status_code == 429
    assert _login(api, email="b@example.com", password="b-password-1").status_code == 200


def test_ip_limit_across_many_emails(api):
    for i in range(5):
        assert _login(api, email=f"user{i}@example.com").status_code == 401
    assert _login(api, email="fresh@example.com").status_code == 429


def test_block_lifts_after_the_window(api, db, signup):
    out = signup()
    for _ in range(3):
        _login(api)
    assert _login(api, password=out["password"]).status_code == 429

    old = datetime.now(UTC) - timedelta(minutes=settings.AUTH_FAILURE_WINDOW_MINUTES + 1)
    db.execute(update(AuthFailure).values(created_at=old))
    db.commit()
    assert _login(api, password=out["password"]).status_code == 200


def test_old_failures_are_cleaned_up(api, db):
    _login(api, email="x@example.com")
    old = datetime.now(UTC) - timedelta(minutes=settings.AUTH_FAILURE_WINDOW_MINUTES + 1)
    db.execute(update(AuthFailure).values(created_at=old))
    db.commit()
    _login(api, email="y@example.com")  # recording a new failure deletes expired rows
    db.expire_all()
    keys = {r.key for r in db.scalars(select(AuthFailure))}
    assert keys == {"email:y@example.com", "ip:testclient"}


def test_invite_accept_wrong_password_is_limited(api, signup):
    manager_a = signup(email="a@example.com", store_name="A")["access_token"]
    signup(email="b@example.com", store_name="B", password="b-password-1")
    token = api.post(
        "/staff/invites",
        json={"email": "b@example.com", "role": "member"},
        headers=auth_header(manager_a),
    ).json()["token"]

    def accept(pw):
        return api.post("/staff/invites/accept", json={"token": token, "password": pw})

    for _ in range(3):
        assert accept("wrong-password").status_code == 401
    assert accept("b-password-1").status_code == 429
    # The same email is also protected on the normal login form.
    assert _login(api, email="b@example.com", password="b-password-1").status_code == 429


def test_bad_invite_tokens_are_limited_by_ip(api):
    for _ in range(5):
        r = api.post("/staff/invites/accept", json={"token": "nope", "password": "whatever-1"})
        assert r.status_code == 400
    r = api.post("/staff/invites/accept", json={"token": "nope", "password": "whatever-1"})
    assert r.status_code == 429
