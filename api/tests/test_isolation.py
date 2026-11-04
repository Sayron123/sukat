"""Tenant isolation (Store A vs Store B) and role permission tests."""

import pytest
from sqlalchemy import select

from app.auth.security import create_access_token
from app.stores.models import Invite, StoreMember
from tests.conftest import auth_header


@pytest.fixture
def two_stores(api, signup):
    """Store A and Store B, each with a manager and one member."""
    out = {}
    for name in ("a", "b"):
        manager = signup(email=f"manager-{name}@example.com", store_name=f"Store {name}")
        invite = api.post(
            "/staff/invites",
            json={"email": f"member-{name}@example.com", "role": "member"},
            headers=auth_header(manager["access_token"]),
        ).json()
        member = api.post(
            "/invites/accept",
            json={"token": invite["token"], "password": "member-pass-1", "full_name": "M"},
        ).json()
        staff = api.get("/staff", headers=auth_header(manager["access_token"])).json()
        out[name] = {
            "manager": manager["access_token"],
            "member": member["access_token"],
            "manager_id": staff[0]["member_id"],
            "member_id": staff[1]["member_id"],
            "store_id": api.get("/auth/me", headers=auth_header(manager["access_token"])).json()[
                "store_id"
            ],
        }
    return out


# ---------- Tenant isolation ----------


def test_store_a_cannot_read_store_b_staff(api, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    res = api.get(f"/staff/{b['member_id']}", headers=auth_header(a["manager"]))
    assert res.status_code == 404


def test_store_a_cannot_deactivate_store_b_staff(api, db, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    res = api.post(f"/staff/{b['member_id']}/deactivate", headers=auth_header(a["manager"]))
    assert res.status_code == 404
    assert db.scalar(select(StoreMember.active).where(StoreMember.id == b["member_id"])) is True


def test_store_a_staff_list_only_shows_store_a(api, two_stores):
    a = two_stores["a"]
    emails = {s["email"] for s in api.get("/staff", headers=auth_header(a["manager"])).json()}
    assert emails == {"manager-a@example.com", "member-a@example.com"}


def test_store_id_in_request_body_is_ignored(api, db, two_stores):
    a, b = two_stores["a"], two_stores["b"]
    res = api.post(
        "/staff/invites",
        json={"email": "new@example.com", "role": "member", "store_id": b["store_id"]},
        headers=auth_header(a["manager"]),
    )
    assert res.status_code == 201
    invite = db.scalar(select(Invite).where(Invite.email == "new@example.com"))
    assert str(invite.store_id) == a["store_id"]


def test_token_for_a_store_you_do_not_belong_to_is_rejected(api, db, two_stores):
    """Even a validly signed token is refused if the user is not an active member there."""
    a, b = two_stores["a"], two_stores["b"]
    user_a = db.scalar(select(StoreMember.user_id).where(StoreMember.id == a["manager_id"]))
    forged, _ = create_access_token(user_a, b["store_id"])
    assert api.get("/staff", headers=auth_header(forged)).status_code == 401


# ---------- Roles ----------


def test_member_cannot_invite(api, two_stores):
    res = api.post(
        "/staff/invites",
        json={"email": "x@example.com", "role": "member"},
        headers=auth_header(two_stores["a"]["member"]),
    )
    assert res.status_code == 403


def test_secretary_cannot_invite_or_deactivate_but_can_list(api, signup):
    manager = signup()["access_token"]
    invite = api.post(
        "/staff/invites",
        json={"email": "sec@example.com", "role": "secretary"},
        headers=auth_header(manager),
    ).json()
    secretary = api.post(
        "/invites/accept",
        json={"token": invite["token"], "password": "sec-pass-123", "full_name": "S"},
    ).json()["access_token"]

    headers = auth_header(secretary)
    assert api.get("/staff", headers=headers).status_code == 200
    assert (
        api.post(
            "/staff/invites", json={"email": "y@example.com", "role": "member"}, headers=headers
        ).status_code
        == 403
    )
    owner_id = api.get("/staff", headers=headers).json()[0]["member_id"]
    assert api.post(f"/staff/{owner_id}/deactivate", headers=headers).status_code == 403


def test_member_cannot_list_or_deactivate(api, two_stores):
    a = two_stores["a"]
    headers = auth_header(a["member"])
    assert api.get("/staff", headers=headers).status_code == 403
    assert api.get(f"/staff/{a['manager_id']}", headers=headers).status_code == 403
    assert api.post(f"/staff/{a['manager_id']}/deactivate", headers=headers).status_code == 403


def test_unauthenticated_requests_are_401(api, two_stores):
    a = two_stores["a"]
    assert api.get("/staff").status_code == 401
    assert api.post("/staff/invites", json={"email": "z@example.com"}).status_code == 401
    assert api.post(f"/staff/{a['member_id']}/deactivate").status_code == 401
