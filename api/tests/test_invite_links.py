from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.auth.schemas import TERMS_VERSION
from tests.conftest import auth_header


def _invite(api, manager, email="new@example.com", role="member"):
    return api.post("/staff/invites", json={"email": email, "role": role}, headers=manager)


def _preview(api, token):
    return api.post("/staff/invites/preview", json={"token": token})


def _accept(api, token, password="Staff-pass-1", full_name="New Person"):
    return api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": token, "password": password, "full_name": full_name},
    )


def test_manager_must_choose_the_role(api, manager):
    res = api.post("/staff/invites", json={"email": "a@example.com"}, headers=manager)
    assert res.status_code == 422


@pytest.mark.parametrize("role", ["owner", ""])
def test_a_link_needs_a_real_role(api, manager, role):
    assert _invite(api, manager, role=role).status_code == 422


@pytest.mark.parametrize("role", ["manager", "secretary", "member"])
def test_the_link_decides_the_role(api, manager, role):
    token = _invite(api, manager, role=role).json()["token"]
    joined = auth_header(_accept(api, token).json()["access_token"])
    assert api.get("/auth/me", headers=joined).json()["role"] == role


def test_the_person_joining_cannot_pick_another_role(api, manager):
    token = _invite(api, manager, role="member").json()["token"]
    res = api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
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


def test_members_cannot_create_links(api, manager):
    token = _invite(api, manager, email="member@example.com", role="member").json()["token"]
    staff = auth_header(_accept(api, token).json()["access_token"])
    assert _invite(api, staff, email="x@example.com").status_code == 403


@pytest.mark.parametrize("terms", [{}, {"accept_terms": False}])
def test_joining_needs_the_terms(api, manager, terms):
    token = _invite(api, manager).json()["token"]
    body = {"token": token, "password": "Staff-pass-1", **terms}
    res = api.post("/staff/invites/accept", json=body)
    assert res.status_code == 422 and "Terms and Privacy Policy" in res.text
    assert _accept(api, token).status_code == 200


def test_joining_records_the_terms(api, db, manager):
    assert _accept(api, _invite(api, manager).json()["token"]).status_code == 200
    version = db.scalar(text("SELECT terms_version FROM users WHERE email = 'new@example.com'"))
    assert version == TERMS_VERSION


def _second_manager(api, owner):
    token = _invite(api, owner, email="second@example.com", role="manager").json()["token"]
    return auth_header(_accept(api, token).json()["access_token"])


def _staff_id(api, headers, email):
    return next(s for s in api.get("/staff", headers=headers).json() if s["email"] == email)[
        "member_id"
    ]


def _demote(api, headers, member_id):
    return api.patch(f"/staff/{member_id}/role", json={"role": "member"}, headers=headers)


def _deactivate(api, headers, member_id):
    return api.post(f"/staff/{member_id}/deactivate", headers=headers)


@pytest.mark.parametrize(("role", "hours"), [("manager", 24), ("secretary", 72), ("member", 72)])
def test_a_manager_link_is_shorter_lived(api, manager, role, hours):
    expires = datetime.fromisoformat(_invite(api, manager, role=role).json()["expires_at"])
    assert abs(expires - datetime.now(UTC) - timedelta(hours=hours)) < timedelta(minutes=1)


def test_only_the_store_creator_is_the_owner(api, manager):
    second = _second_manager(api, manager)
    owners = {s["email"]: s["is_owner"] for s in api.get("/staff", headers=second).json()}
    assert owners == {"owner@example.com": True, "second@example.com": False}


def test_a_second_manager_can_run_the_store(api, manager):
    second = _second_manager(api, manager)
    assert _invite(api, second, email="third@example.com").status_code == 201


@pytest.mark.parametrize("action", [_demote, _deactivate])
def test_another_manager_cannot_touch_the_owner(api, manager, action):
    second = _second_manager(api, manager)
    owner_id = _staff_id(api, second, "owner@example.com")
    res = action(api, second, owner_id)
    assert res.status_code == 403 and "owner" in res.text
    assert api.get("/auth/me", headers=manager).json()["role"] == "manager"


@pytest.mark.parametrize("action", [_demote, _deactivate])
def test_the_owner_can_remove_another_manager(api, manager, action):
    second = _second_manager(api, manager)
    assert action(api, manager, _staff_id(api, manager, "second@example.com")).status_code == 200
    assert _invite(api, second, email="third@example.com").status_code in (401, 403)


@pytest.mark.parametrize("action", [_demote, _deactivate])
def test_a_removed_managers_manager_link_stops_working(api, manager, action):
    second = _second_manager(api, manager)
    token = _invite(api, second, email="third@example.com", role="manager").json()["token"]
    assert _preview(api, token).status_code == 200
    action(api, manager, _staff_id(api, manager, "second@example.com"))
    assert _preview(api, token).status_code == 400
    assert _accept(api, token).status_code == 400


def test_a_removed_managers_staff_link_keeps_working(api, manager):
    second = _second_manager(api, manager)
    token = _invite(api, second, email="third@example.com", role="member").json()["token"]
    _deactivate(api, manager, _staff_id(api, manager, "second@example.com"))
    assert _accept(api, token).status_code == 200


def test_a_store_cannot_have_two_owners(api, db, manager):
    _second_manager(api, manager)
    with pytest.raises(IntegrityError):
        db.execute(text("UPDATE store_members SET is_owner = true"))
    db.rollback()
