from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from tests.conftest import auth_header


def _invite(api, manager, email="new@example.com", role="member"):
    return api.post("/staff/invites", json={"email": email, "role": role}, headers=manager)


def _preview(api, token):
    return api.post("/staff/invites/preview", json={"token": token})


def _accept(api, token, password="Staff-pass-1", full_name="New Person"):
    return api.post(
        "/staff/invites/accept",
        json={"token": token, "password": password, "full_name": full_name},
    )


def test_manager_must_choose_the_role(api, manager):
    res = api.post("/staff/invites", json={"email": "a@example.com"}, headers=manager)
    assert res.status_code == 422


@pytest.mark.parametrize("role", ["manager", "owner", ""])
def test_a_link_can_only_be_secretary_or_member(api, manager, role):
    assert _invite(api, manager, role=role).status_code == 422


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_the_link_decides_the_role(api, manager, role):
    token = _invite(api, manager, role=role).json()["token"]
    joined = auth_header(_accept(api, token).json()["access_token"])
    assert api.get("/auth/me", headers=joined).json()["role"] == role


def test_the_person_joining_cannot_pick_another_role(api, manager):
    token = _invite(api, manager, role="member").json()["token"]
    res = api.post(
        "/staff/invites/accept",
        json={
            "token": token,
            "password": "Staff-pass-1",
            "full_name": "Sneaky",
            "role": "manager",
        },
    )
    joined = auth_header(res.json()["access_token"])
    assert api.get("/auth/me", headers=joined).json()["role"] == "member"


def test_preview_for_a_new_person(api, manager):
    token = _invite(api, manager, role="secretary").json()["token"]
    assert _preview(api, token).json() == {
        "store_name": "Store A",
        "role": "secretary",
        "email": "new@example.com",
        "has_account": False,
    }


def test_preview_knows_an_existing_account(api, manager, signup):
    signup(email="existing@example.com", store_name="Other")
    token = _invite(api, manager, email="existing@example.com").json()["token"]
    assert _preview(api, token).json()["has_account"] is True


def test_preview_does_not_use_up_the_link(api, manager):
    token = _invite(api, manager).json()["token"]
    assert _preview(api, token).status_code == 200
    assert _preview(api, token).status_code == 200
    assert _accept(api, token).status_code == 200


def test_preview_refuses_a_used_link(api, manager):
    token = _invite(api, manager).json()["token"]
    _accept(api, token)
    assert _preview(api, token).status_code == 400


def test_preview_refuses_an_expired_link(api, db, manager):
    token = _invite(api, manager).json()["token"]
    db.execute(
        text("UPDATE invites SET expires_at = :t"),
        {"t": datetime.now(UTC) - timedelta(minutes=1)},
    )
    db.commit()
    assert _preview(api, token).status_code == 400


def test_preview_refuses_a_replaced_link(api, manager):
    old = _invite(api, manager).json()["token"]
    _invite(api, manager, role="secretary")
    assert _preview(api, old).status_code == 400


def test_guessing_preview_links_gets_blocked(api, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "AUTH_MAX_FAILURES_PER_IP", 2)
    assert _preview(api, "nope-1").status_code == 400
    assert _preview(api, "nope-2").status_code == 400
    assert _preview(api, "nope-3").status_code == 429


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_create_links(api, manager, role):
    token = _invite(api, manager, email=f"{role}@example.com", role=role).json()["token"]
    staff = auth_header(_accept(api, token).json()["access_token"])
    assert _invite(api, staff, email="x@example.com").status_code == 403
