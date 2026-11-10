from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.core.outbox import MAX_ATTEMPTS, OutboxEmail, deliver_due_emails
from tests.conftest import FakeMailer

SIGNUP = {
    "store_name": "Store",
    "full_name": "Owner",
    "email": "new@example.com",
    "password": "Correct-horse-1",
    "accept_terms": True,
}


class BrokenMailer:
    def send(self, email) -> None:
        raise OSError("mail server is down")


def _deliver(db_sessionmaker, mailer, now=None) -> None:
    with db_sessionmaker() as session:
        deliver_due_emails(session, mailer, now)


def _waiting(db) -> list[OutboxEmail]:
    db.rollback()
    return list(db.scalars(select(OutboxEmail)))


def test_email_waits_while_the_mail_server_is_down_then_goes_out(api, db, db_sessionmaker):
    api.post("/auth/signup", json=SIGNUP)
    _deliver(db_sessionmaker, BrokenMailer())
    [row] = _waiting(db)
    assert row.attempts == 1

    recovered = FakeMailer(db_sessionmaker)
    _deliver(db_sessionmaker, recovered)
    assert recovered.delivered == []

    _deliver(db_sessionmaker, recovered, datetime.now(UTC) + timedelta(minutes=3))
    assert [e.to for e in recovered.delivered] == ["new@example.com"]
    assert _waiting(db) == []


def test_email_stays_queued_if_nothing_has_sent_it_yet(api, db):
    api.post("/auth/signup", json=SIGNUP)
    assert len(_waiting(db)) == 1


def test_gives_up_after_the_last_attempt(api, db, db_sessionmaker):
    api.post("/auth/signup", json=SIGNUP)
    now = datetime.now(UTC)
    for attempt in range(MAX_ATTEMPTS):
        now += timedelta(hours=2)
        _deliver(db_sessionmaker, BrokenMailer(), now)
        assert len(_waiting(db)) == (0 if attempt == MAX_ATTEMPTS - 1 else 1)


def test_a_failed_signup_queues_no_email(api, db):
    api.post("/auth/signup", json=SIGNUP)
    assert api.post("/auth/signup", json=SIGNUP).status_code == 409
    assert db.scalar(select(func.count()).select_from(OutboxEmail)) == 1


def test_two_workers_never_send_the_same_email(api, db_sessionmaker):
    api.post("/auth/signup", json=SIGNUP)
    other_worker = FakeMailer(db_sessionmaker)
    with db_sessionmaker() as first:
        first.scalars(select(OutboxEmail).with_for_update()).all()
        _deliver(db_sessionmaker, other_worker)
    assert other_worker.delivered == []


def test_sign_in_lasts_ten_years(api):
    token = api.post("/auth/signup", json=SIGNUP).json()
    assert token["expires_in"] == 3650 * 24 * 60 * 60
