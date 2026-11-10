import re
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from app.auth.models import AuthToken, User
from app.core.config import Settings
from tests.conftest import auth_header, upload_photo

SIGNUP = {
    "store_name": "Store",
    "full_name": "Owner",
    "email": "new@example.com",
    "password": "Correct-horse-1",
    "accept_terms": True,
}


def _link_token(email) -> str:
    return re.search(r"token=([\w-]+)", email.body).group(1)


def _login(api, email, password):
    return api.post("/auth/login", json={"email": email, "password": password})


def _forgot(api, mailer, email="owner@example.com") -> str:
    assert api.post("/auth/forgot-password", json={"email": email}).status_code == 204
    return _link_token(mailer.sent[-1])


def _reset(api, token, new_password="Brand-new-pass-1"):
    return api.post("/auth/reset-password", json={"token": token, "new_password": new_password})


def _invite_member(api, manager, email="staff@example.com", role="member"):
    invite = api.post("/staff/invites", json={"email": email, "role": role}, headers=manager).json()
    res = api.post(
        "/staff/invites/accept",
        json={
            "accept_terms": True,
            "token": invite["token"],
            "password": "Staff-pass-1",
            "full_name": "Staff",
        },
    )
    return auth_header(res.json()["access_token"])


def _member_id(api, manager, email="staff@example.com") -> str:
    staff = api.get("/staff", headers=manager).json()
    return next(s["member_id"] for s in staff if s["email"] == email)


def _set_role(api, headers, member_id, role):
    return api.patch(f"/staff/{member_id}/role", json={"role": role}, headers=headers)


def test_signup_emails_a_link_and_me_shows_unverified(api, mailer):
    res = api.post("/auth/signup", json=SIGNUP)
    assert res.status_code == 201
    assert mailer.sent[-1].to == "new@example.com"
    me = api.get("/auth/me", headers=auth_header(res.json()["access_token"])).json()
    assert me["email_verified"] is False


def test_unverified_users_cannot_use_paid_ai_until_they_confirm(api, mailer, storage, reader):
    headers = auth_header(api.post("/auth/signup", json=SIGNUP).json()["access_token"])
    key = upload_photo(api, headers, storage)
    blocked = api.post("/scans", json={"photo_key": key}, headers=headers)
    assert blocked.status_code == 403 and blocked.json()["code"] == "email_not_verified"
    chat = api.post(
        "/insights/chat", json={"messages": [{"role": "user", "content": "hi"}]}, headers=headers
    )
    assert chat.status_code == 403
    assert reader.calls == []

    token = _link_token(mailer.sent[-1])
    assert api.post("/auth/verify-email", json={"token": token}).status_code == 204
    assert api.get("/auth/me", headers=headers).json()["email_verified"] is True
    assert api.post("/scans", json={"photo_key": key}, headers=headers).status_code == 201


def test_verify_link_works_once(api, mailer):
    api.post("/auth/signup", json=SIGNUP)
    token = _link_token(mailer.sent[-1])
    assert api.post("/auth/verify-email", json={"token": token}).status_code == 204
    assert api.post("/auth/verify-email", json={"token": token}).status_code == 400


def test_resend_replaces_the_old_link_and_is_limited(api, mailer):
    headers = auth_header(api.post("/auth/signup", json=SIGNUP).json()["access_token"])
    first = _link_token(mailer.sent[-1])
    assert api.post("/auth/resend-verification", headers=headers).status_code == 204
    assert api.post("/auth/verify-email", json={"token": first}).status_code == 400
    for _ in range(2):
        assert api.post("/auth/resend-verification", headers=headers).status_code == 204
    assert api.post("/auth/resend-verification", headers=headers).status_code == 429


def test_resend_sends_nothing_when_already_verified(api, manager, mailer):
    before = len(mailer.sent)
    assert api.post("/auth/resend-verification", headers=manager).status_code == 204
    assert len(mailer.sent) == before


def test_invited_staff_are_verified(api, manager):
    staff = _invite_member(api, manager)
    assert api.get("/auth/me", headers=staff).json()["email_verified"] is True


def test_forgot_password_looks_the_same_for_unknown_emails(api, signup, mailer):
    signup()
    before = len(mailer.sent)
    known = api.post("/auth/forgot-password", json={"email": "owner@example.com"})
    unknown = api.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content)
    assert len(mailer.sent) == before + 1


def test_forgot_password_is_limited_per_email(api, signup):
    signup()
    for _ in range(3):
        assert (
            api.post("/auth/forgot-password", json={"email": "owner@example.com"}).status_code
            == 204
        )
    assert api.post("/auth/forgot-password", json={"email": "owner@example.com"}).status_code == 429


def test_only_the_hash_of_a_reset_token_is_stored(api, db, signup, mailer):
    signup()
    token = _forgot(api, mailer)
    stored = db.scalars(select(AuthToken).where(AuthToken.purpose == "password_reset")).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64


def test_reset_changes_password_and_signs_out_every_device(api, signup, mailer):
    me = signup()
    old_session = auth_header(me["access_token"])
    assert _reset(api, _forgot(api, mailer)).status_code == 204
    assert "changed" in mailer.sent[-1].subject
    assert api.get("/auth/me", headers=old_session).status_code == 401
    assert _login(api, me["email"], me["password"]).status_code == 401
    assert _login(api, me["email"], "Brand-new-pass-1").status_code == 200


def test_reset_link_works_once(api, signup, mailer):
    signup()
    token = _forgot(api, mailer)
    assert _reset(api, token).status_code == 204
    assert _reset(api, token, "Another-pass-22").status_code == 400


def test_expired_reset_link_is_refused(api, db, signup, mailer):
    signup()
    token = _forgot(api, mailer)
    db.execute(update(AuthToken).values(expires_at=datetime.now(UTC) - timedelta(seconds=1)))
    db.commit()
    assert _reset(api, token).status_code == 400


def test_a_newer_reset_link_cancels_the_older_one(api, signup, mailer):
    signup()
    first = _forgot(api, mailer)
    second = _forgot(api, mailer)
    assert _reset(api, first).status_code == 400
    assert _reset(api, second).status_code == 204


def test_reset_works_when_login_is_locked_and_clears_the_lock(api, signup, mailer):
    me = signup()
    for _ in range(10):
        _login(api, me["email"], "wrong-password")
    assert _login(api, me["email"], me["password"]).status_code == 429
    assert _reset(api, _forgot(api, mailer)).status_code == 204
    assert _login(api, me["email"], "Brand-new-pass-1").status_code == 200


def test_reset_confirms_the_email(api, db, mailer):
    api.post("/auth/signup", json=SIGNUP)
    assert _reset(api, _forgot(api, mailer, SIGNUP["email"])).status_code == 204
    assert db.scalar(select(User.email_verified_at)) is not None


def test_a_verify_link_cannot_reset_a_password(api, mailer):
    api.post("/auth/signup", json=SIGNUP)
    assert _reset(api, _link_token(mailer.sent[-1])).status_code == 400


def test_change_password_keeps_this_device_and_signs_out_others(api, signup, mailer):
    me = signup()
    other_device = auth_header(_login(api, me["email"], me["password"]).json()["access_token"])
    res = api.post(
        "/auth/change-password",
        json={"current_password": me["password"], "new_password": "Brand-new-pass-1"},
        headers=auth_header(me["access_token"]),
    )
    assert res.status_code == 200
    assert api.get("/auth/me", headers=auth_header(res.json()["access_token"])).status_code == 200
    assert api.get("/auth/me", headers=other_device).status_code == 401
    assert _login(api, me["email"], "Brand-new-pass-1").status_code == 200
    assert "changed" in mailer.sent[-1].subject


def test_change_password_needs_the_current_password(api, signup):
    me = signup()
    res = api.post(
        "/auth/change-password",
        json={"current_password": "not-it-at-all", "new_password": "Brand-new-pass-1"},
        headers=auth_header(me["access_token"]),
    )
    assert res.status_code == 400
    assert _login(api, me["email"], me["password"]).status_code == 200


def test_change_password_refuses_the_same_password(api, signup):
    me = signup()
    res = api.post(
        "/auth/change-password",
        json={"current_password": me["password"], "new_password": me["password"]},
        headers=auth_header(me["access_token"]),
    )
    assert res.status_code == 422


def test_change_password_cancels_a_pending_reset_link(api, signup, mailer):
    me = signup()
    token = _forgot(api, mailer)
    api.post(
        "/auth/change-password",
        json={"current_password": me["password"], "new_password": "Brand-new-pass-1"},
        headers=auth_header(me["access_token"]),
    )
    assert _reset(api, token, "Another-pass-22").status_code == 400


def test_logout_ends_the_session_on_the_server(api, signup):
    me = signup()
    headers = auth_header(me["access_token"])
    assert api.post("/auth/logout", headers=headers).status_code == 204
    assert api.get("/auth/me", headers=headers).status_code == 401
    assert _login(api, me["email"], me["password"]).status_code == 200


def test_manager_changes_a_role_and_it_applies_at_once(api, manager):
    staff = _invite_member(api, manager)
    assert api.get("/auth/me", headers=staff).json()["role"] == "member"
    res = _set_role(api, manager, _member_id(api, manager), "secretary")
    assert res.status_code == 200 and res.json()["role"] == "secretary"
    assert api.get("/auth/me", headers=staff).json()["role"] == "secretary"


def test_manager_cannot_change_their_own_role(api, manager):
    me = _member_id(api, manager, "owner@example.com")
    assert _set_role(api, manager, me, "member").status_code == 400


@pytest.mark.parametrize("role", ["member", "secretary"])
def test_only_managers_change_roles(api, manager, role):
    staff = _invite_member(api, manager, role=role)
    assert _set_role(api, staff, _member_id(api, manager), "manager").status_code == 403


def test_role_change_cannot_reach_another_store(api, manager, signup):
    _invite_member(api, manager)
    target = _member_id(api, manager)
    other = auth_header(signup(email="other@example.com", store_name="B")["access_token"])
    assert _set_role(api, other, target, "manager").status_code == 404


def test_inactive_member_role_cannot_change(api, manager):
    _invite_member(api, manager)
    target = _member_id(api, manager)
    api.post(f"/staff/{target}/deactivate", headers=manager)
    assert _set_role(api, manager, target, "secretary").status_code == 409


def test_unknown_role_is_refused(api, manager):
    _invite_member(api, manager)
    assert _set_role(api, manager, _member_id(api, manager), "owner").status_code == 422


def test_console_email_is_refused_outside_development(monkeypatch):
    monkeypatch.delenv("EMAIL_BACKEND", raising=False)
    with pytest.raises(ValidationError):
        Settings(APP_ENV="production", JWT_SECRET="x" * 40, _env_file=None)


def test_smtp_needs_a_host_and_sender(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with pytest.raises(ValidationError):
        Settings(APP_ENV="development", EMAIL_BACKEND="smtp", _env_file=None)
