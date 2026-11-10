import pytest
from sqlalchemy import text

from app.auth.schemas import password_is_strong
from app.auth.security import hash_password
from tests.conftest import auth_header

STRONG = "Fresh_pass1"
WEAK = ["Short_1", "alllower_1", "ALLUPPER_1", "NoNumbers_x", "NoSymbols12", "Has space1"]


def _invite(api, manager, email="new@example.com", role="member"):
    return api.post("/staff/invites", json={"email": email, "role": role}, headers=manager).json()[
        "token"
    ]


def _accept(api, token, password):
    return api.post("/staff/invites/accept", json={"token": token, "password": password})


@pytest.mark.parametrize("password", ["Fresh_pass1", "Aa1!aaaa", "Ab3-xyz9", "Pässw0rd!"])
def test_good_passwords(password):
    assert password_is_strong(password)


@pytest.mark.parametrize("password", WEAK)
def test_bad_passwords(password):
    assert not password_is_strong(password)


@pytest.mark.parametrize("password", WEAK)
def test_signup_refuses_a_weak_password(api, password):
    body = {
        "store_name": "Store",
        "full_name": "Owner",
        "email": "weak@example.com",
        "password": password,
    }
    assert api.post("/auth/signup", json=body).status_code == 422


@pytest.mark.parametrize("password", WEAK)
def test_change_password_refuses_a_weak_password(api, signup, password):
    owner = signup()
    body = {"current_password": owner["password"], "new_password": password}
    headers = auth_header(owner["access_token"])
    assert api.post("/auth/change-password", json=body, headers=headers).status_code == 422


def test_reset_refuses_a_weak_password(api):
    body = {"token": "any", "new_password": "weakpassword"}
    assert api.post("/auth/reset-password", json=body).status_code == 422


@pytest.mark.parametrize("password", WEAK)
def test_new_invitee_needs_a_strong_password(api, manager, password):
    res = _accept(api, _invite(api, manager), password)
    assert res.status_code == 422


def test_a_refused_password_does_not_use_up_the_invite(api, manager):
    token = _invite(api, manager)
    assert _accept(api, token, "weakpassword").status_code == 422
    assert _accept(api, token, STRONG).status_code == 200


def test_new_invitee_only_needs_a_password(api, manager):
    joined = _accept(api, _invite(api, manager, role="secretary"), STRONG)
    me = api.get("/auth/me", headers=auth_header(joined.json()["access_token"])).json()
    assert (me["email"], me["full_name"], me["role"]) == ("new@example.com", "new", "secretary")


def test_older_passwords_still_sign_in_and_accept_invites(api, db, manager, signup):
    signup(email="old@example.com", store_name="Old")
    db.execute(
        text("UPDATE users SET password_hash = :h WHERE email = 'old@example.com'"),
        {"h": hash_password("oldstylepassword")},
    )
    db.commit()
    login = {"email": "old@example.com", "password": "oldstylepassword"}
    assert api.post("/auth/login", json=login).status_code == 200
    assert (
        _accept(api, _invite(api, manager, "old@example.com"), "oldstylepassword").status_code
        == 200
    )
