from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text

from tests.conftest import auth_header

OWNER = "owner@example.com"
TODAY = datetime.now(ZoneInfo("Asia/Manila")).date()


def _invite(api, headers, email, role="member"):
    return api.post("/staff/invites", json={"email": email, "role": role}, headers=headers)


def _accept(api, token):
    return api.post(
        "/staff/invites/accept",
        json={"accept_terms": True, "token": token, "password": "Staff-pass-1"},
    )


def _join(api, headers, email="staff@example.com", role="member"):
    token = _invite(api, headers, email, role).json()["token"]
    return auth_header(_accept(api, token).json()["access_token"])


def _row(api, headers, email):
    return next(s for s in api.get("/staff", headers=headers).json() if s["email"] == email)


def _id(api, headers, email="staff@example.com"):
    return _row(api, headers, email)["member_id"]


def _alias(api, headers, member_id, alias):
    return api.patch(f"/staff/{member_id}/alias", json={"alias": alias}, headers=headers)


def _mark(api, headers, member_id, day=TODAY, status="present", note=None):
    body = {"work_date": day.isoformat(), "status": status, "note": note}
    return api.post(f"/staff/{member_id}/attendance", json=body, headers=headers)


def _history(api, headers, member_id):
    return api.get(f"/staff/{member_id}/attendance", headers=headers)


def test_manager_gives_someone_an_alias(api, manager):
    _join(api, manager)
    res = _alias(api, manager, _id(api, manager), "  Kuya Ben  ")
    assert res.status_code == 200 and res.json()["alias"] == "Kuya Ben"
    assert res.json()["full_name"] == "staff"


def test_a_blank_alias_clears_it(api, manager):
    _join(api, manager)
    target = _id(api, manager)
    _alias(api, manager, target, "Ben")
    assert _alias(api, manager, target, "   ").json()["alias"] is None


def test_an_alias_has_a_length_limit(api, manager):
    _join(api, manager)
    assert _alias(api, manager, _id(api, manager), "x" * 121).status_code == 422


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_set_an_alias(api, manager, role):
    staff = _join(api, manager, role=role)
    assert _alias(api, staff, _id(api, manager), "Boss").status_code == 403


def test_another_manager_cannot_rename_the_owner(api, manager):
    second = _join(api, manager, role="manager")
    assert _alias(api, second, _id(api, second, OWNER), "Nope").status_code == 403


def test_the_owner_can_set_their_own_alias(api, manager):
    assert _alias(api, manager, _id(api, manager, OWNER), "Boss").status_code == 200


def test_a_co_manager_can_rename_staff(api, manager):
    second = _join(api, manager, email="second@example.com", role="manager")
    _join(api, manager)
    assert _alias(api, second, _id(api, second), "Ben").status_code == 200


def test_an_alias_cannot_reach_another_store(api, manager, signup):
    _join(api, manager)
    other = auth_header(signup(email="other@example.com", store_name="B")["access_token"])
    assert _alias(api, other, _id(api, manager), "Ben").status_code == 404


def test_an_alias_belongs_to_one_store(api, manager, signup):
    _join(api, manager)
    _alias(api, manager, _id(api, manager), "Ben")
    other = auth_header(signup(email="other@example.com", store_name="B")["access_token"])
    token = _invite(api, other, "staff@example.com").json()["token"]
    assert _accept(api, token).status_code == 200
    assert _row(api, other, "staff@example.com")["alias"] is None


def test_attendance_is_saved_newest_first(api, manager):
    _join(api, manager)
    target = _id(api, manager)
    older = TODAY - timedelta(days=1)
    assert _mark(api, manager, target, older, "late", "traffic").status_code == 200
    assert _mark(api, manager, target).status_code == 200
    rows = _history(api, manager, target).json()
    assert [r["status"] for r in rows] == ["present", "late"]
    assert rows[1]["work_date"] == older.isoformat() and rows[1]["note"] == "traffic"


def test_saving_the_same_day_replaces_it(api, manager):
    _join(api, manager)
    target = _id(api, manager)
    first = _mark(api, manager, target, note="first").json()
    second = _mark(api, manager, target, status="absent").json()
    assert second["id"] == first["id"] and second["status"] == "absent" and second["note"] is None
    assert second["updated_at"] >= first["updated_at"]
    assert len(_history(api, manager, target).json()) == 1


def test_attendance_cannot_be_in_the_future(api, manager):
    _join(api, manager)
    res = _mark(api, manager, _id(api, manager), TODAY + timedelta(days=1))
    assert res.status_code == 422 and "future" in res.text


def test_attendance_needs_a_real_status(api, manager):
    _join(api, manager)
    assert _mark(api, manager, _id(api, manager), status="vacation").status_code == 422


def test_attendance_notes_have_a_length_limit(api, manager):
    _join(api, manager)
    assert _mark(api, manager, _id(api, manager), note="x" * 301).status_code == 422


def test_inactive_staff_cannot_get_attendance(api, manager):
    _join(api, manager)
    target = _id(api, manager)
    api.post(f"/staff/{target}/deactivate", headers=manager)
    assert _mark(api, manager, target).status_code == 409


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_use_attendance(api, manager, role):
    staff = _join(api, manager, role=role)
    target = _id(api, manager)
    assert _mark(api, staff, target).status_code == 403
    assert _history(api, staff, target).status_code == 403


def test_attendance_cannot_reach_another_store(api, manager, signup):
    _join(api, manager)
    target = _id(api, manager)
    other = auth_header(signup(email="other@example.com", store_name="B")["access_token"])
    assert _mark(api, other, target).status_code == 404
    assert _history(api, other, target).status_code == 404


def _day(api, headers, day=TODAY):
    return api.get("/attendance", params={"work_date": day.isoformat()}, headers=headers)


def test_a_day_lists_everyones_attendance(api, manager):
    _join(api, manager)
    _join(api, manager, "second@example.com")
    first, second = _id(api, manager), _id(api, manager, "second@example.com")
    _mark(api, manager, first, status="late", note="traffic")
    _mark(api, manager, second)
    _mark(api, manager, second, TODAY - timedelta(days=1), "absent")
    rows = {r["member_id"]: r for r in _day(api, manager).json()}
    assert set(rows) == {first, second}
    assert rows[first]["status"] == "late" and rows[first]["note"] == "traffic"
    assert rows[second]["status"] == "present"
    assert [r["status"] for r in _day(api, manager, TODAY - timedelta(days=1)).json()] == ["absent"]


def test_a_day_needs_a_real_date(api, manager):
    assert api.get("/attendance", params={"work_date": "soon"}, headers=manager).status_code == 422
    assert api.get("/attendance", headers=manager).status_code == 422


@pytest.mark.parametrize("role", ["secretary", "member"])
def test_only_managers_see_a_days_attendance(api, manager, role):
    assert _day(api, _join(api, manager, role=role)).status_code == 403


def test_a_day_stays_inside_one_store(api, manager, signup):
    _join(api, manager)
    _mark(api, manager, _id(api, manager))
    other = auth_header(signup(email="other@example.com", store_name="B")["access_token"])
    assert _day(api, other).json() == []


def test_a_secretary_can_invite_a_member(api, manager):
    secretary = _join(api, manager, email="sec@example.com", role="secretary")
    res = _invite(api, secretary, "new@example.com")
    assert res.status_code == 201
    joined = auth_header(_accept(api, res.json()["token"]).json()["access_token"])
    assert api.get("/auth/me", headers=joined).json()["role"] == "member"


@pytest.mark.parametrize("role", ["secretary", "manager"])
def test_a_secretary_cannot_invite_above_member(api, manager, role):
    secretary = _join(api, manager, email="sec@example.com", role="secretary")
    res = _invite(api, secretary, "new@example.com", role)
    assert res.status_code == 403 and "only invite members" in res.text


def test_a_secretary_cannot_bring_back_a_removed_person(api, manager):
    secretary = _join(api, manager, email="sec@example.com", role="secretary")
    _join(api, manager)
    api.post(f"/staff/{_id(api, manager)}/deactivate", headers=manager)
    assert _invite(api, secretary, "staff@example.com").status_code == 403
    assert _invite(api, manager, "staff@example.com").status_code == 201


def test_a_secretary_cannot_replace_a_managers_higher_link(api, manager):
    secretary = _join(api, manager, email="sec@example.com", role="secretary")
    token = _invite(api, manager, "new@example.com", "secretary").json()["token"]
    assert _invite(api, secretary, "new@example.com").status_code == 409
    joined = auth_header(_accept(api, token).json()["access_token"])
    assert api.get("/auth/me", headers=joined).json()["role"] == "secretary"


def test_a_secretary_can_replace_an_expired_higher_link(api, db, manager):
    secretary = _join(api, manager, email="sec@example.com", role="secretary")
    _invite(api, manager, "new@example.com", "secretary")
    db.execute(
        text("UPDATE invites SET expires_at = :t WHERE email = 'new@example.com'"),
        {"t": datetime.now(UTC) - timedelta(minutes=1)},
    )
    db.commit()
    assert _invite(api, secretary, "new@example.com").status_code == 201


def test_a_member_sees_the_staff_list_without_emails(api, manager):
    member = _join(api, manager)
    rows = api.get("/staff", headers=member).json()
    assert len(rows) == 2 and all(s["email"] is None for s in rows)
    assert "@" not in api.get("/staff", headers=member).text


def test_a_secretary_still_sees_staff_emails(api, manager):
    secretary = _join(api, manager, role="secretary")
    emails = {s["email"] for s in api.get("/staff", headers=secretary).json()}
    assert emails == {OWNER, "staff@example.com"}


@pytest.mark.parametrize("role", ["member", "secretary"])
def test_only_managers_change_roles(api, manager, role):
    _join(api, manager)
    other = _join(api, manager, "other@example.com", role)
    target = _id(api, manager)
    res = api.patch(f"/staff/{target}/role", json={"role": "secretary"}, headers=other)
    assert res.status_code == 403
    assert _row(api, manager, "staff@example.com")["role"] == "member"


def test_anyone_can_rename_themselves(api, manager):
    member = _join(api, manager)
    res = api.patch("/auth/me", json={"full_name": "  Ben Cruz  "}, headers=member)
    assert res.status_code == 200 and res.json()["full_name"] == "Ben Cruz"
    assert api.get("/auth/me", headers=member).json()["full_name"] == "Ben Cruz"
    assert _row(api, manager, "staff@example.com")["full_name"] == "Ben Cruz"
    assert _row(api, manager, OWNER)["full_name"] != "Ben Cruz"


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_a_bad_name_is_refused(api, manager, name):
    assert api.patch("/auth/me", json={"full_name": name}, headers=manager).status_code == 422


def test_renaming_needs_sign_in(api):
    assert api.patch("/auth/me", json={"full_name": "Ben"}).status_code == 401
