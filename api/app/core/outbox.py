import logging
import threading
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.base import Base, created_at_col, uuid_pk
from app.core.config import settings
from app.core.db import SessionLocal
from app.core.mailer import Email, Mailer, get_mailer

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 6


class OutboxEmail(Base):
    __tablename__ = "email_outbox"

    id: Mapped[UUID] = uuid_pk()
    to_address: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = created_at_col()


def enqueue_email(db: Session, email: Email) -> None:
    db.add(OutboxEmail(to_address=email.to, subject=email.subject, body=email.body))


def _next_due(db: Session, now: datetime) -> OutboxEmail | None:
    return db.scalar(
        select(OutboxEmail)
        .where(OutboxEmail.next_attempt_at <= now)
        .order_by(OutboxEmail.next_attempt_at, OutboxEmail.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def deliver_due_emails(db: Session, mailer: Mailer, now: datetime | None = None) -> None:
    now = now or datetime.now(UTC)
    while (row := _next_due(db, now)) is not None:
        try:
            mailer.send(Email(to=row.to_address, subject=row.subject, body=row.body))
        except Exception:
            logger.exception("Could not send outbox email %s", row.id)
            row.attempts += 1
            if row.attempts >= MAX_ATTEMPTS:
                logger.error("Gave up on outbox email %s", row.id)
                db.delete(row)
            else:
                row.next_attempt_at = now + timedelta(minutes=2**row.attempts)
        else:
            db.delete(row)
        db.commit()


def run_email_worker(stop: threading.Event) -> None:
    mailer = get_mailer()
    while not stop.wait(settings.EMAIL_POLL_SECONDS):
        try:
            with SessionLocal() as db:
                deliver_due_emails(db, mailer)
        except Exception:
            logger.exception("Email worker failed")
