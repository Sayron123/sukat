"""Staff and invites. Every function is scoped to one store; raises AppError subclasses."""

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
from app.auth.schemas import PASSWORD_RULES_MESSAGE, TokenOut, password_is_strong
from app.auth.security import hash_password, hash_token, verify_password
from app.auth.service import issue_token
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Forbidden, Invalid, NotFound, Unauthorized
from app.stores.models import Invite, Role, Store, StoreMember
from app.stores.schemas import InvitePreviewOut


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
        token_hash=hash_token(token),
        invited_by_user_id=invited_by,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITE_EXPIRE_HOURS),
    )
    db.add(row)
    db.commit()
    return row, token


def _open_invite(db: Session, token: str, ip: str | None, *, lock: bool = False) -> Invite:
    ensure_not_limited(db, limits_for(None, ip))
    query = select(Invite).where(Invite.token_hash == hash_token(token))
    row = db.scalar(query.with_for_update() if lock else query)
    if row is None or row.accepted_at is not None or row.expires_at <= datetime.now(UTC):
        key = ip_key(ip)
        if key:
            record_failure(db, [key])
        raise BadRequest("This invite is invalid or has expired")
    return row


def preview_invite(db: Session, token: str, ip: str | None) -> InvitePreviewOut:
    row = _open_invite(db, token, ip)
    store = db.get(Store, row.store_id)
    assert store is not None
    has_account = db.scalar(select(User.id).where(User.email == row.email)) is not None
    return InvitePreviewOut(
        store_name=store.name, role=Role(row.role), email=row.email, has_account=has_account
    )


def accept_invite(
    db: Session, token: str, password: str, full_name: str | None, ip: str | None
) -> TokenOut:
    """Join a store with an invite token and return a token for that store. Commits.

    New email: creates the account (the name defaults to the start of the email, and the
    password must meet the rules). Existing account: the invitee
    must give its current password. A deactivated member is re-activated with the
    invite's role. Bad tokens count against the IP; wrong passwords against the email too.

    @raises BadRequest (invalid/expired), Unauthorized (wrong password), Invalid (weak
        password), Conflict (already active staff), TooManyRequests
    """
    row = _open_invite(db, token, ip, lock=True)

    limits = limits_for(row.email, ip)
    ensure_not_limited(db, limits)

    user = db.scalar(select(User).where(User.email == row.email))
    if user is None:
        if not password_is_strong(password):
            raise Invalid(PASSWORD_RULES_MESSAGE)
        name = (full_name or "").strip() or row.email.split("@")[0][:120]
        user = User(email=row.email, full_name=name, password_hash=hash_password(password))
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
    user.email_verified_at = user.email_verified_at or row.accepted_at
    db.commit()
    return issue_token(user, row.store_id)


def _lock_staff_changes(db: Session, store_id: UUID, acting_member_id: UUID) -> None:
    db.execute(select(Store.id).where(Store.id == store_id).with_for_update())
    acting = db.scalar(
        select(StoreMember)
        .where(StoreMember.id == acting_member_id)
        .execution_options(populate_existing=True)
    )
    if acting is None or not acting.active or acting.role != Role.MANAGER:
        raise Forbidden("You do not have permission to do this")


def change_role(
    db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID, role: Role
) -> StoreMember:
    if member_id == acting_member_id:
        raise BadRequest("You cannot change your own role")
    _lock_staff_changes(db, store_id, acting_member_id)
    member = get_member(db, store_id, member_id)
    if not member.active:
        raise Conflict("This person is inactive. Invite them again to bring them back.")
    member.role = role
    db.commit()
    return member


def deactivate(db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID) -> StoreMember:
    """Turn off a member's access (takes effect on their next request). Commits.

    @raises BadRequest when deactivating yourself, so a store can't lock itself out
    """
    member = get_member(db, store_id, member_id)
    if member.id == acting_member_id:
        raise BadRequest("You cannot deactivate yourself")
    _lock_staff_changes(db, store_id, acting_member_id)
    member.active = False
    db.commit()
    return member
