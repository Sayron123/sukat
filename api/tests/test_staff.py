from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.stores.models import Invite
from tests.conftest import auth_header


def _invite(api, token, email="staff@example.com", role="member"):
    return api.post(
        "/staff/invites", json={"email": email, "role": role}, headers=auth_header(token)
    )


def _accept(api, invite_token, password="staff-pass-1", full_name="Staff One"):
    return api.post(
        "/invites/accept",
        json={"token": invite_token, "password": password, "full_name": full_name},
    )


def test_invite_accept_list_deactivate_flow(api, db, signup):
    manager = signup()["access_token"]

    res = _invite(api, manager, email="Staff@Example.com", role="secretary")
    assert res.status_code == 201
    invite = res.json()
    assert invite["email"] == "staff@example.com" and invite["role"] == "secretary"
    # Only the hash is stored, never the raw token.
    stored = db.scalar(select(Invite))
    assert stored.token_hash != invite["token"] and len(stored.token_hash) == 64

    accepted = _accept(api, invite["token"])
    assert accepted.status_code == 200
    staff_token = accepted.json()["access_token"]
    assert api.get("/auth/me", headers=auth_header(staff_token)).json()["role"] == "secretary"

    staff = api.get("/staff", headers=auth_header(manager)).json()
    assert [s["email"] for s in staff] == ["owner@example.com", "staff@example.com"]
    staff_id = staff[1]["member_id"]

    one = api.get(f"/staff/{staff_id}", headers=auth_header(manager))
    assert one.status_code == 200 and one.json()["full_name"] == "Staff One"

    off = api.post(f"/staff/{staff_id}/deactivate", headers=auth_header(manager))
    assert off.status_code == 200 and off.json()["active"] is False

    # Deactivation takes effect immediately, even for an existing token...
    assert api.get("/auth/me", headers=auth_header(staff_token)).status_code == 401
    # ...and for new logins.
    login = api.post("/auth/login", json={"email": "staff@example.com", "password": "staff-pass-1"})
    assert login.status_code == 403


def test_invite_cannot_be_reused(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    assert _accept(api, token).status_code == 200
    assert _accept(api, token).status_code == 400


def test_expired_invite_is_rejected(api, db, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    invite = db.scalar(select(Invite))
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert _accept(api, token).status_code == 400


def test_bad_invite_token_is_rejected(api):
    assert _accept(api, "not-a-real-token").status_code == 400


def test_new_invite_replaces_old_unaccepted_one(api, signup):
    manager = signup()["access_token"]
    old = _invite(api, manager).json()["token"]
    new = _invite(api, manager).json()["token"]
    assert _accept(api, old).status_code == 400
    assert _accept(api, new).status_code == 200


def test_cannot_invite_active_staff(api, signup):
    manager = signup()["access_token"]
    assert _invite(api, manager, email="owner@example.com").status_code == 409


def test_existing_user_joins_with_own_password(api, signup):
    manager_a = signup(email="a@example.com", store_name="A")["access_token"]
    signup(email="b@example.com", store_name="B", password="b-password-1")
    token = _invite(api, manager_a, email="b@example.com").json()["token"]

    assert _accept(api, token, password="wrong-password").status_code == 401
    res = _accept(api, token, password="b-password-1")
    assert res.status_code == 200
    me = api.get("/auth/me", headers=auth_header(res.json()["access_token"])).json()
    assert me["store_name"] == "A" and me["role"] == "member"


def test_reinvite_reactivates_deactivated_staff(api, signup):
    manager = signup()["access_token"]
    _accept(api, _invite(api, manager).json()["token"])
    staff_id = api.get("/staff", headers=auth_header(manager)).json()[1]["member_id"]
    api.post(f"/staff/{staff_id}/deactivate", headers=auth_header(manager))

    token = _invite(api, manager, role="secretary").json()["token"]
    assert _accept(api, token).status_code == 200
    again = api.get(f"/staff/{staff_id}", headers=auth_header(manager)).json()
    assert again["active"] is True and again["role"] == "secretary"


def test_new_user_needs_full_name(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    assert _accept(api, token, full_name="").status_code == 422


def test_manager_cannot_deactivate_self(api, signup):
    manager = signup()["access_token"]
    me = api.get("/staff", headers=auth_header(manager)).json()[0]["member_id"]
    assert api.post(f"/staff/{me}/deactivate", headers=auth_header(manager)).status_code == 400
