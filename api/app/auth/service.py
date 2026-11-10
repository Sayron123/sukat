"""Accounts: signup and login. No HTTP here; raises AppError subclasses."""

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.deps import CurrentMember
from app.auth.models import AuthToken, TokenPurpose, User
from app.auth.rate_limit import (
    clear_failures,
    count_email_request,
    email_key,
    ensure_not_limited,
    ip_key,
    limits_for,
    record_failure,
)
from app.auth.schemas import MeOut, SignupIn, TokenOut
from app.auth.security import create_access_token, hash_password, hash_token, verify_password
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Forbidden, Invalid, Unauthorized
from app.core.mailer import Email
from app.core.outbox import enqueue_email
from app.stores.models import Role, Store, StoreMember

EMAIL_TAKEN = "An account with this email already exists"


def issue_token(user: User, store_id: UUID) -> TokenOut:
    token, expires_in = create_access_token(user.id, store_id, user.token_version)
    return TokenOut(access_token=token, expires_in=expires_in)


def _link(path: str, token: str) -> str:
    return f"{settings.WEB_APP_URL.rstrip('/')}/{path}?token={token}"


def _verify_email_message(to: str, token: str) -> Email:
    return Email(
        to=to,
        subject="Confirm your email for Sukat",
        body=(
            "Open this link to confirm your email:\n\n"
            f"{_link('verify-email', token)}\n\n"
            f"It works for {settings.EMAIL_VERIFY_EXPIRE_HOURS} hours."
        ),
    )


def _password_changed_message(to: str) -> Email:
    return Email(
        to=to,
        subject="Your Sukat password was changed",
        body=(
            "Your password was just changed and your other devices were signed out.\n\n"
            "If this was not you, use Forgot password on the sign-in page right away."
        ),
    )


def _new_token(db: Session, user_id: UUID, purpose: TokenPurpose, lifetime: timedelta) -> str:
    db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.used_at.is_(None),
        )
    )
    token = secrets.token_urlsafe(32)
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=hash_token(token),
            expires_at=datetime.now(UTC) + lifetime,
        )
    )
    return token


def _consume_token(db: Session, token: str, purpose: TokenPurpose, ip: str | None) -> User:
    ensure_not_limited(db, limits_for(None, ip))
    row = db.scalar(
        select(AuthToken)
        .where(AuthToken.token_hash == hash_token(token), AuthToken.purpose == purpose)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at <= now:
        key = ip_key(ip)
        if key:
            record_failure(db, [key])
        raise BadRequest("This link is invalid or has expired")
    row.used_at = now
    db.flush()
    user = db.get(User, row.user_id)
    assert user is not None
    return user


def _revoke_sessions(user: User) -> None:
    user.token_version = User.token_version + 1


def _set_password(db: Session, user: User, new_password: str) -> None:
    user.password_hash = hash_password(new_password)
    _revoke_sessions(user)
    db.execute(
        delete(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == TokenPurpose.PASSWORD_RESET,
            AuthToken.used_at.is_(None),
        )
    )


def signup(db: Session, data: SignupIn, ip: str | None) -> TokenOut:
    """Create a store, its first user, and a manager membership in ONE transaction.

    @raises Conflict if the email is taken (also when two signups race)
    """
    count_email_request(db, "signup", None, ip)
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise Conflict(EMAIL_TAKEN)

    store = Store(name=data.store_name, address=data.store_address)
    user = User(
        email=data.email, full_name=data.full_name, password_hash=hash_password(data.password)
    )
    db.add_all([store, user])
    db.flush()  # assigns ids, still inside the same transaction
    db.add(StoreMember(store_id=store.id, user_id=user.id, role=Role.MANAGER))
    verify_token = _new_token(
        db,
        user.id,
        TokenPurpose.EMAIL_VERIFY,
        timedelta(hours=settings.EMAIL_VERIFY_EXPIRE_HOURS),
    )
    enqueue_email(db, _verify_email_message(user.email, verify_token))
    try:
        db.commit()  # all three rows are saved together, or none are
    except IntegrityError as e:
        db.rollback()
        # Two signups with the same email at the same moment: the unique constraint catches it.
        if getattr(getattr(e.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            raise Conflict(EMAIL_TAKEN) from None
        raise
    return issue_token(user, store.id)


def login(db: Session, email: str, password: str, ip: str | None) -> TokenOut:
    """Check email + password; return a token for the user's first active store.

    Too many failures for the same email (or IP) inside the window raise
    TooManyRequests even if the password is right, so guessing cannot continue.

    @param email already normalized (lowercase) by the schema
    @raises Unauthorized (same message for wrong password and unknown email),
        Forbidden if the account has no active store, TooManyRequests
    """
    limits = limits_for(email, ip)
    ensure_not_limited(db, limits)

    user = db.scalar(select(User).where(User.email == email))
    # Always run the hash check (even for unknown emails) so timing does not reveal accounts.
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok:
        # Unknown emails are counted too, so the 429 does not reveal which emails exist.
        record_failure(db, [key for key, _ in limits])
        raise Unauthorized("Incorrect email or password")
    clear_failures(db, email_key(email))
    db.commit()

    # A user signs in to their first active store. Store switching comes later.
    member = db.scalar(
        select(StoreMember)
        .where(StoreMember.user_id == user.id, StoreMember.active.is_(True))
        .order_by(StoreMember.created_at, StoreMember.id)
        .limit(1)
    )
    if member is None:
        raise Forbidden("Your account is not active in any store")
    return issue_token(user, member.store_id)


def logout(db: Session, user: User) -> None:
    _revoke_sessions(user)
    db.commit()


def change_password(
    db: Session,
    user: User,
    store_id: UUID,
    current_password: str,
    new_password: str,
    ip: str | None,
) -> TokenOut:
    limits = limits_for(user.email, ip)
    ensure_not_limited(db, limits)
    if not verify_password(current_password, user.password_hash):
        record_failure(db, [key for key, _ in limits])
        raise BadRequest("Your current password is incorrect")
    if new_password == current_password:
        raise Invalid("Choose a password different from your current one")
    clear_failures(db, email_key(user.email))
    _set_password(db, user, new_password)
    enqueue_email(db, _password_changed_message(user.email))
    db.commit()
    return issue_token(user, store_id)


def request_password_reset(db: Session, email: str, ip: str | None) -> None:
    count_email_request(db, "reset", email, ip)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        return
    token = _new_token(
        db,
        user.id,
        TokenPurpose.PASSWORD_RESET,
        timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
    )
    enqueue_email(
        db,
        Email(
            to=user.email,
            subject="Reset your Sukat password",
            body=(
                "Open this link to set a new password:\n\n"
                f"{_link('reset-password', token)}\n\n"
                f"It works for {settings.PASSWORD_RESET_EXPIRE_MINUTES} minutes. "
                "If you did not ask for this, you can ignore this email."
            ),
        ),
    )
    db.commit()


def reset_password(db: Session, token: str, new_password: str, ip: str | None) -> None:
    user = _consume_token(db, token, TokenPurpose.PASSWORD_RESET, ip)
    _set_password(db, user, new_password)
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    clear_failures(db, email_key(user.email))
    enqueue_email(db, _password_changed_message(user.email))
    db.commit()


def verify_email(db: Session, token: str, ip: str | None) -> None:
    user = _consume_token(db, token, TokenPurpose.EMAIL_VERIFY, ip)
    user.email_verified_at = user.email_verified_at or datetime.now(UTC)
    db.commit()


def resend_verification(db: Session, user: User, ip: str | None) -> None:
    if user.email_verified_at is not None:
        return
    count_email_request(db, "verify", user.email, ip)
    token = _new_token(
        db,
        user.id,
        TokenPurpose.EMAIL_VERIFY,
        timedelta(hours=settings.EMAIL_VERIFY_EXPIRE_HOURS),
    )
    enqueue_email(db, _verify_email_message(user.email, token))
    db.commit()


def get_me(db: Session, current: CurrentMember) -> MeOut:
    store = db.get(Store, current.store_id)
    assert store is not None
    return MeOut(
        user_id=current.user.id,
        email=current.user.email,
        full_name=current.user.full_name,
        email_verified=current.user.email_verified_at is not None,
        store_id=store.id,
        store_name=store.name,
        store_address=store.address,
        role=current.role,
    )
