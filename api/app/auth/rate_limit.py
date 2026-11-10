"""Failed-attempt limits for login and invite acceptance, stored in Postgres.

Stored in the database (not in memory) so limits survive restarts and are shared by
every API worker/instance.

Keys look like "email:juan@example.com" or "ip:203.0.113.5".
- The email key cannot be faked by the caller, so it is the main protection for an account.
- The ip key is best-effort: it depends on the proxy in front passing the real client IP
  (see FORWARDED_ALLOW_IPS in docs/phase-1.md).
"""

from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth.models import AuthFailure
from app.core.config import settings
from app.core.errors import TooManyRequests


def email_key(email: str) -> str:
    return f"email:{email.lower()}"


def client_ip(request: Request) -> str | None:
    """Client IP as seen by the API (uvicorn rewrites it from X-Forwarded-For for trusted
    proxies). None when unknown. Used by routers; services take the plain IP string."""
    return request.client.host if request.client else None


def ip_key(ip: str | None) -> str | None:
    """None when the IP is unknown, so we never lump all unknown callers into one bucket."""
    return f"ip:{ip}" if ip else None


def limits_for(email: str | None, ip: str | None) -> list[tuple[str, int]]:
    """The (key, max_failures) pairs that apply to this attempt."""
    pairs: list[tuple[str, int]] = []
    if email:
        pairs.append((email_key(email), settings.AUTH_MAX_FAILURES_PER_EMAIL))
    key = ip_key(ip)
    if key:
        pairs.append((key, settings.AUTH_MAX_FAILURES_PER_IP))
    return pairs


def email_send_limits(kind: str, email: str | None, ip: str | None) -> list[tuple[str, int]]:
    pairs: list[tuple[str, int]] = []
    if email:
        pairs.append((f"{kind}:{email.lower()}", settings.AUTH_EMAILS_MAX_PER_EMAIL))
    if ip:
        pairs.append((f"{kind}:ip:{ip}", settings.AUTH_EMAILS_MAX_PER_IP))
    return pairs


def _window_start(now: datetime) -> datetime:
    return now - timedelta(minutes=settings.AUTH_FAILURE_WINDOW_MINUTES)


def ensure_not_limited(db: Session, limits: list[tuple[str, int]]) -> None:
    """Raise 429 (with Retry-After) if any key reached its limit inside the window.

    Note: check-then-record is not atomic, so a burst of parallel requests can get a few
    extra tries past the limit. That is acceptable for slowing down password guessing.
    """
    now = datetime.now(UTC)
    since = _window_start(now)
    for key, max_failures in limits:
        count, oldest = db.execute(
            select(func.count(), func.min(AuthFailure.created_at)).where(
                AuthFailure.key == key, AuthFailure.created_at > since
            )
        ).one()
        if count >= max_failures:
            # The block lifts when the oldest failure in the window ages out.
            retry_after = int((oldest - since).total_seconds()) + 1
            raise TooManyRequests(
                "Too many failed attempts. Please wait and try again.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )


def record_failure(db: Session, keys: list[str]) -> None:
    """Save one failed attempt per key, and delete rows older than the window.

    Commits immediately, because the caller is about to raise an error response.
    Assumes the session has no other pending changes that should be rolled back.
    """
    now = datetime.now(UTC)
    db.execute(delete(AuthFailure).where(AuthFailure.created_at <= _window_start(now)))
    db.add_all([AuthFailure(key=k, created_at=now) for k in keys])
    db.commit()


def count_email_request(db: Session, kind: str, email: str | None, ip: str | None) -> None:
    limits = email_send_limits(kind, email, ip)
    ensure_not_limited(db, limits)
    record_failure(db, [key for key, _ in limits])


def clear_failures(db: Session, key: str) -> None:
    """Reset a key after a successful attempt (e.g. the right password for that email).
    Does not commit; the caller commits with its own changes."""
    db.execute(delete(AuthFailure).where(AuthFailure.key == key))
