from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.stores.models import Invite
from tests.conftest import auth_header


def _invite(api, token, role="member", name=None):
    return api.post("/staff/invites", json={"role": role, "name": name}, headers=auth_header(token))


def _accept(api, invite_token, password="Staff-pass-1", full_name="Staff One", username="staff"):
    return api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
            "token": invite_token,
            "username": username,
            "password": password,
            "full_name": full_name,
        },
    )


def _join_existing(api, invite_token, login, password):
    return api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": invite_token, "login": login, "password": password},
    )


def _login(api, login, password="Staff-pass-1"):
    return api.post("/auth/login", json={"login": login, "password": password})


def test_invite_accept_list_deactivate_flow(api, db, signup):
    manager = signup()["access_token"]

    res = _invite(api, manager, role="secretary", name="  Juan  ")
    assert res.status_code == 201
    invite = res.json()
    assert invite["name"] == "Juan" and invite["role"] == "secretary"
    # Only the hash is stored, never the raw token.
    stored = db.scalar(select(Invite))
    assert stored.token_hash != invite["token"] and len(stored.token_hash) == 64
    assert stored.email is None

    accepted = _accept(api, invite["token"], username="  Juan.DC ")
    assert accepted.status_code == 200
    staff_token = accepted.json()["access_token"]
    me = api.get("/auth/me", headers=auth_header(staff_token)).json()
    assert (me["role"], me["username"], me["email"]) == ("secretary", "juan.dc", None)

    staff = api.get("/staff", headers=auth_header(manager)).json()
    assert [s["email"] or s["username"] for s in staff] == ["owner@example.com", "juan.dc"]
    staff_id = staff[1]["member_id"]

    one = api.get(f"/staff/{staff_id}", headers=auth_header(manager))
    assert one.status_code == 200 and one.json()["full_name"] == "Staff One"

    off = api.post(f"/staff/{staff_id}/deactivate", headers=auth_header(manager))
    assert off.status_code == 200 and off.json()["active"] is False

    # Deactivation takes effect immediately, even for an existing token...
    assert api.get("/auth/me", headers=auth_header(staff_token)).status_code == 401
    # ...and for new logins.
    assert _login(api, "juan.dc").status_code == 403


def test_a_username_signs_in_like_an_email(api, signup):
    manager = signup()["access_token"]
    _accept(api, _invite(api, manager).json()["token"], username="maria")
    assert _login(api, "Maria").status_code == 200
    assert _login(api, "maria", "Wrong-pass-1").status_code == 401
    old_form = api.post("/auth/login", json={"email": "maria", "password": "Staff-pass-1"})
    assert old_form.status_code == 200


def test_username_rules_and_taken_usernames(api, signup):
    manager = signup()["access_token"]
    for bad in ("ab", "1abc", "juan dc", "juan@dc", "x" * 31):
        token = _invite(api, manager).json()["token"]
        assert _accept(api, token, username=bad).status_code == 422
    _accept(api, _invite(api, manager).json()["token"], username="juan")
    taken = _accept(api, _invite(api, manager).json()["token"], username="JUAN")
    assert taken.status_code == 409


def test_a_new_account_needs_a_name(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    assert _accept(api, token, full_name="  ").status_code == 422
    assert _accept(api, token).status_code == 200


def test_accept_needs_either_a_new_username_or_an_existing_login(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    both = {"accept_terms": True, "token": token, "username": "juan", "login": "juan"}
    neither = {"accept_terms": True, "token": token, "full_name": "Juan"}
    for body in (both, neither):
        res = api.post("/staff/invites/accept", json={**body, "password": "Staff-pass-1"})
        assert res.status_code == 422


def test_invite_cannot_be_reused(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    assert _accept(api, token).status_code == 200
    assert _accept(api, token, username="other").status_code == 400


def test_expired_invite_is_rejected(api, db, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    invite = db.scalar(select(Invite))
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert _accept(api, token).status_code == 400


def test_bad_invite_token_is_rejected(api):
    assert _accept(api, "not-a-real-token").status_code == 400


def test_each_invite_is_its_own_link(api, signup):
    manager = signup()["access_token"]
    first = _invite(api, manager).json()["token"]
    second = _invite(api, manager).json()["token"]
    assert _accept(api, first, username="first").status_code == 200
    assert _accept(api, second, username="second").status_code == 200


def test_existing_user_joins_with_own_password(api, signup):
    manager_a = signup(email="a@example.com", store_name="A")["access_token"]
    signup(email="b@example.com", store_name="B", password="B-password-1")
    token = _invite(api, manager_a).json()["token"]

    assert _join_existing(api, token, "b@example.com", "wrong-password").status_code == 401
    res = _join_existing(api, token, "B@Example.com", "B-password-1")
    assert res.status_code == 200
    me = api.get("/auth/me", headers=auth_header(res.json()["access_token"])).json()
    assert me["store_name"] == "A" and me["role"] == "member"


def test_active_staff_cannot_join_again(api, signup):
    manager = signup()["access_token"]
    token = _invite(api, manager).json()["token"]
    assert _join_existing(api, token, "owner@example.com", "Correct-horse-1").status_code == 409


def test_reinvite_reactivates_deactivated_staff(api, signup):
    manager = signup()["access_token"]
    _accept(api, _invite(api, manager).json()["token"])
    staff_id = api.get("/staff", headers=auth_header(manager)).json()[1]["member_id"]
    api.post(f"/staff/{staff_id}/deactivate", headers=auth_header(manager))

    token = _invite(api, manager, role="secretary").json()["token"]
    assert _join_existing(api, token, "staff", "Staff-pass-1").status_code == 200
    again = api.get(f"/staff/{staff_id}", headers=auth_header(manager)).json()
    assert again["active"] is True and again["role"] == "secretary"


def test_a_secretarys_invite_cannot_bring_back_a_removed_person(api, signup):
    manager = signup()["access_token"]
    secretary = _accept(api, _invite(api, manager, "secretary").json()["token"], username="sec")
    sec = secretary.json()["access_token"]
    _accept(api, _invite(api, manager).json()["token"])
    staff_id = api.get("/staff", headers=auth_header(manager)).json()[2]["member_id"]
    api.post(f"/staff/{staff_id}/deactivate", headers=auth_header(manager))

    token = _invite(api, sec).json()["token"]
    assert _join_existing(api, token, "staff", "Staff-pass-1").status_code == 403


def test_manager_cannot_deactivate_self(api, signup):
    manager = signup()["access_token"]
    me = api.get("/staff", headers=auth_header(manager)).json()[0]["member_id"]
    assert api.post(f"/staff/{me}/deactivate", headers=auth_header(manager)).status_code == 400


def test_pending_invites_list_only_open_ones_newest_first(api, db, signup):
    manager = signup()["access_token"]
    _invite(api, manager, name="First")
    _invite(api, manager, role="secretary", name="Second")
    accepted = _invite(api, manager, name="Joined").json()
    _accept(api, accepted["token"])
    _invite(api, manager, name="Old")
    old = db.scalar(select(Invite).where(Invite.name == "Old"))
    old.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()

    res = api.get("/staff/invites", headers=auth_header(manager))
    assert res.status_code == 200
    rows = res.json()
    assert [r["name"] for r in rows] == ["Second", "First"]
    assert rows[0]["role"] == "secretary" and "token" not in rows[0]


def test_renewing_an_invite_gives_a_new_link_and_kills_the_old_one(api, signup):
    manager = signup()["access_token"]
    first = _invite(api, manager, name="Juan").json()
    renewed = api.post(f"/staff/invites/{first['id']}/renew", headers=auth_header(manager))
    assert renewed.status_code == 200
    assert renewed.json()["id"] == first["id"] and renewed.json()["name"] == "Juan"
    assert _accept(api, first["token"]).status_code == 400
    assert _accept(api, renewed.json()["token"]).status_code == 200
    gone = api.post(f"/staff/invites/{first['id']}/renew", headers=auth_header(manager))
    assert gone.status_code == 404


def test_a_secretary_renews_only_member_invites(api, signup):
    manager = signup()["access_token"]
    sec = _accept(api, _invite(api, manager, "secretary").json()["token"], username="sec")
    headers = auth_header(sec.json()["access_token"])
    for_member = _invite(api, manager).json()
    for_secretary = _invite(api, manager, "secretary").json()
    renew = "/staff/invites/{}/renew"
    assert api.post(renew.format(for_member["id"]), headers=headers).status_code == 200
    assert api.post(renew.format(for_secretary["id"]), headers=headers).status_code == 403


def test_another_stores_invite_cannot_be_renewed(api, signup):
    manager_a = signup(email="a@example.com", store_name="A")["access_token"]
    manager_b = signup(email="b@example.com", store_name="B")["access_token"]
    invite = _invite(api, manager_a).json()
    res = api.post(f"/staff/invites/{invite['id']}/renew", headers=auth_header(manager_b))
    assert res.status_code == 404


def test_members_cannot_see_pending_invites(api, signup):
    manager = signup()["access_token"]
    staff = _accept(api, _invite(api, manager).json()["token"]).json()["access_token"]
    assert api.get("/staff/invites", headers=auth_header(staff)).status_code == 403
