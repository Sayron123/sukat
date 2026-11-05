from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth.models import User
from app.core.config import settings
from app.stores.models import Store, StoreMember
from tests.conftest import auth_header


def test_signup_creates_store_user_and_manager(api, db, signup):
    out = signup(email="Owner@Example.com", store_name="  Bayan Hardware ")

    assert out["token_type"] == "bearer"
    user = db.scalar(select(User))
    assert user.email == "owner@example.com"  # normalized
    assert user.password_hash.startswith("$argon2")  # never plain text
    member = db.scalar(select(StoreMember))
    assert member.role == "manager" and member.active and member.user_id == user.id
    assert db.scalar(select(Store.name)) == "Bayan Hardware"
    assert member.created_at.tzinfo is not None
    assert member.created_at.utcoffset() == timedelta(0)  # UTC

    me = api.get("/auth/me", headers=auth_header(out["access_token"]))
    assert me.status_code == 200
    assert me.json()["role"] == "manager"
    assert me.json()["store_name"] == "Bayan Hardware"


def test_signup_duplicate_email_is_409_and_creates_nothing(api, db, signup):
    signup(email="a@example.com")
    res = api.post(
        "/auth/signup",
        json={
            "store_name": "Other",
            "full_name": "X",
            "email": "A@example.com",
            "password": "another-pass-1",
        },
    )
    assert res.status_code == 409
    assert db.scalar(select(func.count()).select_from(Store)) == 1


def test_signup_is_one_transaction(api, db, monkeypatch):
    """If the last insert (membership) fails, the store and user are not saved either."""
    import app.auth.service as auth_service

    class BadRole:
        MANAGER = "owner"  # violates the role CHECK constraint at commit time

    monkeypatch.setattr(auth_service, "Role", BadRole)
    with pytest.raises(IntegrityError):
        api.post(
            "/auth/signup",
            json={
                "store_name": "S",
                "full_name": "F",
                "email": "t@example.com",
                "password": "x" * 8,
            },
        )
    for model in (Store, User, StoreMember):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_signup_validates_input(api):
    res = api.post(
        "/auth/signup",
        json={"store_name": "S", "full_name": "F", "email": "not-an-email", "password": "short"},
    )
    assert res.status_code == 422


def test_login_ok(api, signup):
    out = signup()
    res = api.post("/auth/login", json={"email": "OWNER@example.com", "password": out["password"]})
    assert res.status_code == 200
    token = res.json()["access_token"]
    claims = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert claims["store_id"] == api.get("/auth/me", headers=auth_header(token)).json()["store_id"]


def test_login_wrong_password_and_unknown_email_look_the_same(api, signup):
    signup()
    wrong = api.post("/auth/login", json={"email": "owner@example.com", "password": "nope-nope"})
    unknown = api.post("/auth/login", json={"email": "ghost@example.com", "password": "nope-nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_requires_valid_token(api, signup):
    out = signup()
    assert api.get("/auth/me").status_code == 401
    assert api.get("/auth/me", headers=auth_header("garbage")).status_code == 401

    tampered = jwt.encode(
        jwt.decode(out["access_token"], options={"verify_signature": False}),
        "wrong-secret-that-is-long-enough-for-hs256",
        algorithm="HS256",
    )
    assert api.get("/auth/me", headers=auth_header(tampered)).status_code == 401

    claims = jwt.decode(out["access_token"], options={"verify_signature": False})
    claims["exp"] = datetime.now(UTC) - timedelta(minutes=1)
    expired = jwt.encode(claims, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    assert api.get("/auth/me", headers=auth_header(expired)).status_code == 401


def test_production_refuses_default_jwt_secret():
    from pydantic import ValidationError

    from app.core.config import Settings

    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", _env_file=None)
    Settings(APP_ENV="production", JWT_SECRET="x" * 40, _env_file=None)  # ok


def test_missing_or_mistyped_app_env_refuses_public_jwt_secret(monkeypatch):
    # Audit H2: fail closed. Only the exact value "development" allows the public secret.
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # no APP_ENV -> production
    for typo in ("prod", "Production", "development ", "dev"):
        monkeypatch.setenv("APP_ENV", typo)
        with pytest.raises(ValidationError):
            Settings(_env_file=None)
    monkeypatch.setenv("APP_ENV", "prod")
    with pytest.raises(ValidationError):
        Settings(JWT_SECRET="too-short", _env_file=None)
    Settings(JWT_SECRET="x" * 40, _env_file=None)  # ok: private secret
    monkeypatch.setenv("APP_ENV", "development")
    Settings(_env_file=None)  # ok on a developer's PC
