"""Request IDs on responses and log lines; Sentry events carry no personal data."""

import logging

import pytest

from app.core.observability import scrub_event, scrub_text


def test_every_response_has_a_request_id(api):
    res = api.get("/auth/me")  # a 401: errors get one too
    rid = res.headers["x-request-id"]
    assert res.status_code == 401 and len(rid) == 32
    assert api.get("/auth/me").headers["x-request-id"] != rid  # a new one each time


def test_a_safe_incoming_request_id_is_kept_and_a_bad_one_replaced(api):
    kept = api.get("/auth/me", headers={"X-Request-ID": "web-1234abcd"})
    assert kept.headers["x-request-id"] == "web-1234abcd"
    bad = api.get("/auth/me", headers={"X-Request-ID": "x\r\nSet-Cookie: a=b"})
    assert bad.headers["x-request-id"] != "x\r\nSet-Cookie: a=b"
    assert len(bad.headers["x-request-id"]) == 32


def test_log_lines_carry_the_request_id(api, caplog):
    from app.core.observability import RequestIdFilter

    handler_filter = RequestIdFilter()
    caplog.handler.addFilter(handler_filter)
    with caplog.at_level(logging.INFO, logger="app.request"):
        res = api.get("/auth/me?token=secret-value", headers={"X-Request-ID": "trace-0001"})
    [line] = [r for r in caplog.records if r.name == "app.request"]
    assert line.request_id == "trace-0001"  # type: ignore[attr-defined]
    assert line.getMessage().startswith("GET /v1/auth/me 401")
    assert "secret-value" not in line.getMessage()  # no query strings in logs
    assert res.headers["x-request-id"] == "trace-0001"


@pytest.mark.parametrize(
    ("text", "kept_out"),
    [
        ("login failed for juan.dela.cruz@example.com", "juan.dela.cruz@example.com"),
        ("auth Bearer eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl", "eyJhbGciOi"),
        ("token eyJhbGciOi.eyJzdWIiOi.c2lnbmF0dXJl here", "c2lnbmF0dXJl"),
        ("key sk-ant-api03-abcdefghijk", "sk-ant-api03"),
        ("gemini AIzaSyA1234567890abcdefghijklmn", "AIzaSy"),
    ],
)
def test_scrub_text(text, kept_out):
    assert kept_out not in scrub_text(text)


def test_sentry_events_lose_personal_data():
    event = {
        "request": {
            "method": "POST",
            "url": "https://api.example.com/v1/auth/login?email=a@b.co",
            "headers": {"Authorization": "Bearer eyJa.eyJb.sig", "Cookie": "sukat_session=x"},
            "cookies": {"sukat_session": "x"},
            "data": {"email": "a@b.co", "password": "hunter22"},
            "query_string": "email=a@b.co",
            "env": {"REMOTE_ADDR": "1.2.3.4"},
        },
        "user": {"ip_address": "1.2.3.4", "email": "a@b.co"},
        "server_name": "host-1",
        "message": "failed for maria@store.ph",
        "exception": {
            "values": [
                {
                    "value": "no user maria@store.ph",
                    "stacktrace": {"frames": [{"function": "login", "vars": {"password": "x"}}]},
                }
            ]
        },
        "breadcrumbs": {"values": [{"message": "GET /x", "data": {"url": "/x?token=t"}}]},
        "tags": {"request_id": "trace-0001"},
    }
    out = scrub_event(event)
    text = str(out)
    for secret in ("a@b.co", "hunter22", "eyJa", "sukat_session", "1.2.3.4", "maria@store.ph"):
        assert secret not in text, secret
    assert "vars" not in text and "host-1" not in text
    assert out["request"] == {"method": "POST", "url": "https://api.example.com/v1/auth/login"}
    assert out["tags"]["request_id"] == "trace-0001"  # what helps debugging stays


def test_sentry_starts_only_with_a_dsn_and_without_pii(monkeypatch):
    import sentry_sdk

    from app.core import observability
    from app.core.config import Settings

    seen = {}
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    assert not observability.init_sentry(Settings(_env_file=None, APP_ENV="development"))
    assert seen == {}
    dsn = "https://key@o1.ingest.sentry.io/1"
    started = Settings(_env_file=None, APP_ENV="development", SENTRY_DSN=dsn)
    assert observability.init_sentry(started)
    assert seen["send_default_pii"] is False and seen["include_local_variables"] is False
    assert seen["max_request_body_size"] == "never"
    assert seen["before_send"] is observability.scrub_event


def test_uvicorns_access_log_is_off():
    # It would log full URLs with query strings; our own access line logs the path only.
    from app.core.observability import setup_logging

    setup_logging("INFO")
    assert logging.getLogger("uvicorn.access").disabled
