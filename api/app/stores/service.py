"""Staff and invites. Every function is scoped to one store; raises AppError subclasses."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.rate_limit import (
    clear_failures,
    email_key,
    ensure_not_limited,
    ip_key,
    limits_for,
    record_failure,
)
from app.auth.schemas import TokenOut
from app.auth.security import hash_password, verify_password
from app.auth.service import issue_token
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Invalid, NotFound, Unauthorized
from app.stores.models import Invite, Role, StoreMember


def hash_invite_token(token: str) -> str:
    """Only this hash is stored, so a leaked database can't be used to accept invites."""
    return hashlib.sha256(token.encode()).hexdigest()


def get_member(db: Session, store_id: UUID, member_id: UUID) -> StoreMember:
    """A member of THIS store.

    @raises NotFound also for another store's member, so callers can't learn it exists
    """
    member = db.scalar(
        select(StoreMember).where(StoreMember.id == member_id, StoreMember.store_id == store_id)
    )
    if member is None:
        raise NotFound("Staff member not found")
    return member


def list_members(db: Session, store_id: UUID) -> list[StoreMember]:
    return list(
        db.scalars(
            select(StoreMember)
            .where(StoreMember.store_id == store_id)
            .order_by(StoreMember.created_at, StoreMember.id)
        )
    )


def invite(
    db: Session, store_id: UUID, invited_by: UUID, email: str, role: Role
) -> tuple[Invite, str]:
    """Create an invite and return it with the raw token (shown once; only its hash is
    stored). Replaces any older unaccepted invite for the same email. Commits.

    @param email already normalized (lowercase) by the schema
    @raises Conflict if the person is already active staff
    """
    already_active = db.scalar(
        select(StoreMember.id)
        .join(User, User.id == StoreMember.user_id)
        .where(
            StoreMember.store_id == store_id,
            StoreMember.active.is_(True),
            User.email == email,
        )
    )
    if already_active is not None:
        raise Conflict("This person is already active staff")

    db.execute(
        delete(Invite).where(
            Invite.store_id == store_id, Invite.email == email, Invite.accepted_at.is_(None)
        )
    )
    token = secrets.token_urlsafe(32)
    row = Invite(
        store_id=store_id,
        email=email,
        role=role,
        token_hash=hash_invite_token(token),
        invited_by_user_id=invited_by,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITE_EXPIRE_HOURS),
    )
    db.add(row)
    db.commit()
    return row, token


def accept_invite(
    db: Session, token: str, password: str, full_name: str | None, ip: str | None
) -> TokenOut:
    """Join a store with an invite token and return a token for that store. Commits.

    New email: creates the account (full_name required). Existing account: the invitee
    must give its current password. A deactivated member is re-activated with the
    invite's role. Bad tokens count against the IP; wrong passwords against the email too.

    @raises BadRequest (invalid/expired), Unauthorized (wrong password), Invalid (no
        name), Conflict (already active staff), TooManyRequests
    """
    ensure_not_limited(db, limits_for(None, ip))
    # FOR UPDATE locks the invite row, so the same invite cannot be accepted twice at once.
    row = db.scalar(
        select(Invite).where(Invite.token_hash == hash_invite_token(token)).with_for_update()
    )
    if row is None or row.accepted_at is not None or row.expires_at <= datetime.now(UTC):
        key = ip_key(ip)
        if key:
            record_failure(db, [key])
        raise BadRequest("This invite is invalid or has expired")

    limits = limits_for(row.email, ip)
    ensure_not_limited(db, limits)

    user = db.scalar(select(User).where(User.email == row.email))
    if user is None:
        if not full_name or not full_name.strip():
            raise Invalid("full_name is required")
        user = User(
            email=row.email, full_name=full_name.strip(), password_hash=hash_password(password)
        )
        db.add(user)
        db.flush()
    elif not verify_password(password, user.password_hash):
        record_failure(db, [key for key, _ in limits])
        raise Unauthorized("Incorrect password for this account")
    else:
        clear_failures(db, email_key(row.email))

    member = db.scalar(
        select(StoreMember).where(
            StoreMember.store_id == row.store_id, StoreMember.user_id == user.id
        )
    )
    if member is None:
        db.add(StoreMember(store_id=row.store_id, user_id=user.id, role=row.role))
    elif member.active:
        raise Conflict("You are already staff in this store")
    else:
        member.active = True  # a re-invite brings a deactivated person back
        member.role = row.role

    row.accepted_at = datetime.now(UTC)
    db.commit()
    return issue_token(user.id, row.store_id)


def deactivate(db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID) -> StoreMember:
    """Turn off a member's access (takes effect on their next request). Commits.

    @raises BadRequest when deactivating yourself, so a store can't lock itself out
    """
    member = get_member(db, store_id, member_id)
    if member.id == acting_member_id:
        raise BadRequest("You cannot deactivate yourself")
    member.active = False
    db.commit()
    return member
