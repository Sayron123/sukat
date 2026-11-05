"""Accounts: signup and login. No HTTP here; raises AppError subclasses."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.rate_limit import (
    clear_failures,
    email_key,
    ensure_not_limited,
    limits_for,
    record_failure,
)
from app.auth.schemas import SignupIn, TokenOut
from app.auth.security import create_access_token, hash_password, verify_password
from app.core.errors import Conflict, Forbidden, Unauthorized
from app.stores.models import Role, Store, StoreMember

EMAIL_TAKEN = "An account with this email already exists"


def issue_token(user_id, store_id) -> TokenOut:
    token, expires_in = create_access_token(user_id, store_id)
    return TokenOut(access_token=token, expires_in=expires_in)


def signup(db: Session, data: SignupIn) -> TokenOut:
    """Create a store, its first user, and a manager membership in ONE transaction.

    @raises Conflict if the email is taken (also when two signups race)
    """
    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise Conflict(EMAIL_TAKEN)

    store = Store(name=data.store_name, address=data.store_address)
    user = User(
        email=data.email, full_name=data.full_name, password_hash=hash_password(data.password)
    )
    db.add_all([store, user])
    db.flush()  # assigns ids, still inside the same transaction
    db.add(StoreMember(store_id=store.id, user_id=user.id, role=Role.MANAGER))
    try:
        db.commit()  # all three rows are saved together, or none are
    except IntegrityError as e:
        db.rollback()
        # Two signups with the same email at the same moment: the unique constraint catches it.
        if getattr(getattr(e.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            raise Conflict(EMAIL_TAKEN) from None
        raise
    return issue_token(user.id, store.id)


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
    return issue_token(user.id, member.store_id)
