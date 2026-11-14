import pytest
from pydantic import SecretStr
from sqlalchemy import select

from app.auth import google
from app.auth.google import GoogleUser
from app.auth.models import User, UserIdentity
from app.core.config import settings
from app.core.errors import BadRequest
from tests.conftest import auth_header

FLOW = {
    "code": "code-from-google",
    "code_verifier": "v" * 43,
    "redirect_uri": "http://localhost:3000/api/auth/google/callback",
    "nonce": "n" * 16,
}
JUAN = GoogleUser(subject="google-sub-1", email="juan@gmail.com", name="Juan Dela Cruz")


@pytest.fixture
def as_google(monkeypatch):
    who = {"user": JUAN}

    def fake(code, verifier, redirect_uri, nonce):
        assert (code, verifier, redirect_uri, nonce) == (
            FLOW["code"],
            FLOW["code_verifier"],
            FLOW["redirect_uri"],
            FLOW["nonce"],
        )
        return who["user"]

    monkeypatch.setattr(google, "google_user", fake)
    return who


def _invite(api, headers, role="member"):
    return api.post("/staff/invites", json={"role": role}, headers=headers).json()["token"]


def _join_google(api, token):
    body = {**FLOW, "token": token, "accept_terms": True}
    return api.post("/staff/invites/accept-google", json=body)


def _signup_google(api, store_name="Juan Hardware"):
    body = {**FLOW, "store_name": store_name, "accept_terms": True}
    return api.post("/auth/google/signup", json=body)


def test_a_new_person_joins_by_invite_with_google_and_signs_in_again(api, db, manager, as_google):
    joined = _join_google(api, _invite(api, manager))
    assert joined.status_code == 200
    me = api.get("/auth/me", headers=auth_header(joined.json()["access_token"])).json()
    assert (me["email"], me["full_name"], me["role"]) == (
        "juan@gmail.com",
        "Juan Dela Cruz",
        "member",
    )
    assert me["google"] is True and me["email_verified"] is True
    user = db.scalar(select(User).where(User.email == "juan@gmail.com"))
    assert user.password_hash is None and user.terms_version is not None

    again = api.post("/auth/google/login", json=FLOW)
    assert again.status_code == 200
    assert (
        api.get("/auth/me", headers=auth_header(again.json()["access_token"])).json()["role"]
        == "member"
    )


def test_an_unknown_google_account_cannot_sign_in(api, as_google):
    res = api.post("/auth/google/login", json=FLOW)
    assert res.status_code == 401 and "invite link" in res.json()["detail"]


def test_a_new_owner_sets_up_a_store_with_google(api, as_google):
    res = _signup_google(api)
    assert res.status_code == 201
    me = api.get("/auth/me", headers=auth_header(res.json()["access_token"])).json()
    assert me["store_name"] == "Juan Hardware" and me["role"] == "manager"
    assert me["email_confirmation"] is False
    assert _signup_google(api, "Second Store").status_code == 409


def test_google_never_takes_over_an_account_by_email(api, signup, manager, as_google):
    signup(email="juan@gmail.com", store_name="Other")
    assert _join_google(api, _invite(api, manager)).status_code == 409
    assert _signup_google(api).status_code == 409
    assert api.post("/auth/google/login", json=FLOW).status_code == 401


def test_a_password_account_connects_google_in_settings(api, db, signup, as_google):
    me = signup(email="juan@gmail.com", store_name="Juan Store")
    headers = auth_header(me["access_token"])
    assert api.post("/auth/google/connect", json=FLOW, headers=headers).status_code == 204
    assert api.get("/auth/me", headers=headers).json()["google"] is True
    assert api.post("/auth/google/connect", json=FLOW, headers=headers).status_code == 204
    assert api.post("/auth/google/login", json=FLOW).status_code == 200


def test_connecting_proves_a_matching_email(api, db, as_google):
    created = api.post(
        "/auth/signup",
        json={
            "store_name": "S",
            "full_name": "Juan",
            "email": "juan@gmail.com",
            "password": "Correct-horse-1",
            "accept_terms": True,
        },
    ).json()
    headers = auth_header(created["access_token"])
    assert api.get("/auth/me", headers=headers).json()["email_verified"] is False
    api.post("/auth/google/connect", json=FLOW, headers=headers)
    assert api.get("/auth/me", headers=headers).json()["email_verified"] is True


def test_one_google_account_belongs_to_one_sukat_account(api, signup, manager, as_google):
    _join_google(api, _invite(api, manager))
    other = auth_header(signup(email="maria@example.com", store_name="M")["access_token"])
    res = api.post("/auth/google/connect", json=FLOW, headers=other)
    assert res.status_code == 409 and "another Sukat account" in res.json()["detail"]


def test_an_account_connects_only_one_google_account(api, signup, as_google):
    headers = auth_header(signup(email="maria@example.com", store_name="M")["access_token"])
    api.post("/auth/google/connect", json=FLOW, headers=headers)
    as_google["user"] = GoogleUser(subject="google-sub-2", email="maria@gmail.com", name="Maria")
    assert api.post("/auth/google/connect", json=FLOW, headers=headers).status_code == 409


def test_a_google_only_account_has_no_password_to_change(api, manager, as_google):
    joined = auth_header(_join_google(api, _invite(api, manager)).json()["access_token"])
    body = {"current_password": "anything", "new_password": "Brand-new-pass-1"}
    res = api.post("/auth/change-password", json=body, headers=joined)
    assert res.status_code == 400 and "Google" in res.json()["detail"]


def test_google_joining_needs_the_terms(api, manager, as_google):
    body = {**FLOW, "token": _invite(api, manager)}
    assert api.post("/staff/invites/accept-google", json=body).status_code == 422


def test_the_client_id_is_shared_only_when_google_is_set_up(api, monkeypatch):
    assert api.get("/auth/google").json() == {"client_id": None}
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", SecretStr("secret"))
    assert api.get("/auth/google").json() == {"client_id": "id.apps.googleusercontent.com"}


def test_google_is_refused_when_not_set_up(api):
    res = api.post("/auth/google/login", json=FLOW)
    assert res.status_code == 400 and "isn't set up" in res.json()["detail"]


@pytest.mark.parametrize(
    "redirect_uri",
    [
        "https://evil.example/api/auth/google/callback",
        "http://localhost:3000/somewhere-else",
    ],
)
def test_only_our_own_callback_is_accepted(monkeypatch, redirect_uri):
    monkeypatch.setattr(settings, "CORS_ORIGINS", "http://localhost:3000")
    with pytest.raises(BadRequest):
        google.check_redirect(redirect_uri)
    google.check_redirect("http://localhost:3000/api/auth/google/callback")


def _claims(**changes):
    claims = {
        "iss": "https://accounts.google.com",
        "sub": "google-sub-1",
        "email": "Juan@Gmail.com",
        "email_verified": True,
        "name": "Juan",
        "nonce": "n" * 16,
    }
    claims.update(changes)
    return claims


@pytest.mark.parametrize(
    "changes",
    [
        {"nonce": "x" * 16},
        {"iss": "https://evil.example"},
        {"email_verified": False},
        {"email": ""},
    ],
)
def test_bad_google_answers_are_refused(monkeypatch, changes):
    monkeypatch.setattr(google.id_token, "verify_oauth2_token", lambda *a: _claims(**changes))
    with pytest.raises(BadRequest):
        google.verify("token", "n" * 16)


def test_a_good_google_answer_gives_the_person(monkeypatch):
    monkeypatch.setattr(google.id_token, "verify_oauth2_token", lambda *a: _claims())
    assert google.verify("token", "n" * 16) == GoogleUser("google-sub-1", "juan@gmail.com", "Juan")


def test_a_forged_token_is_refused(monkeypatch):
    def forged(*args):
        raise ValueError("Wrong signature")

    monkeypatch.setattr(google.id_token, "verify_oauth2_token", forged)
    with pytest.raises(BadRequest):
        google.verify("token", "n" * 16)


def test_the_link_is_kept_by_googles_id(db, api, manager, as_google):
    _join_google(api, _invite(api, manager))
    assert db.scalar(select(UserIdentity.subject)) == "google-sub-1"
