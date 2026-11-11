"""Staff and invites. Every function is scoped to one store; raises AppError subclasses."""

import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
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
from app.auth.schemas import (
    PASSWORD_RULES_MESSAGE,
    TERMS_VERSION,
    TokenOut,
    password_is_strong,
)
from app.auth.security import hash_password, hash_token, verify_password
from app.auth.service import issue_token
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Forbidden, Invalid, NotFound, Unauthorized
from app.stores.models import Attendance, AttendanceStatus, Invite, Role, Store, StoreMember
from app.stores.schemas import InvitePreviewOut

_STORE_TZ = ZoneInfo(settings.STORE_TIMEZONE)
ATTENDANCE_SHOWN = 31


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


def _limit_secretary_invite(db: Session, store_id: UUID, email: str, role: Role) -> None:
    if role != Role.MEMBER:
        raise Forbidden("Secretaries can only invite members")
    removed = db.scalar(
        select(StoreMember.id)
        .join(User, User.id == StoreMember.user_id)
        .where(
            StoreMember.store_id == store_id,
            StoreMember.active.is_(False),
            User.email == email,
        )
    )
    if removed is not None:
        raise Forbidden("This person was removed from the store. Ask a manager to invite them.")
    higher_invite = db.scalar(
        select(Invite.id).where(
            Invite.store_id == store_id,
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.expires_at > datetime.now(UTC),
            Invite.role != Role.MEMBER,
        )
    )
    if higher_invite is not None:
        raise Conflict("A manager already invited this person. Ask a manager to change it.")


def invite(
    db: Session, store_id: UUID, invited_by: UUID, inviter_role: str, email: str, role: Role
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
    if inviter_role == Role.SECRETARY:
        _limit_secretary_invite(db, store_id, email, role)

    db.execute(
        delete(Invite).where(
            Invite.store_id == store_id, Invite.email == email, Invite.accepted_at.is_(None)
        )
    )
    token = secrets.token_urlsafe(32)
    hours = (
        settings.MANAGER_INVITE_EXPIRE_HOURS
        if role == Role.MANAGER
        else settings.INVITE_EXPIRE_HOURS
    )
    row = Invite(
        store_id=store_id,
        email=email,
        role=role,
        token_hash=hash_token(token),
        invited_by_user_id=invited_by,
        expires_at=datetime.now(UTC) + timedelta(hours=hours),
    )
    db.add(row)
    db.commit()
    return row, token


def _inviter_is_still_manager(db: Session, row: Invite, *, lock: bool) -> bool:
    if lock:
        db.execute(select(Store.id).where(Store.id == row.store_id).with_for_update())
    return (
        db.scalar(
            select(StoreMember.id).where(
                StoreMember.store_id == row.store_id,
                StoreMember.user_id == row.invited_by_user_id,
                StoreMember.active.is_(True),
                StoreMember.role == Role.MANAGER,
            )
        )
        is not None
    )


def _open_invite(db: Session, token: str, ip: str | None, *, lock: bool = False) -> Invite:
    ensure_not_limited(db, limits_for(None, ip))
    query = select(Invite).where(Invite.token_hash == hash_token(token))
    row = db.scalar(query.with_for_update() if lock else query)
    if (
        row is None
        or row.accepted_at is not None
        or row.expires_at <= datetime.now(UTC)
        or (row.role == Role.MANAGER and not _inviter_is_still_manager(db, row, lock=lock))
    ):
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

    user.terms_accepted_at = datetime.now(UTC)
    user.terms_version = TERMS_VERSION

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


def _refuse_if_owner(member: StoreMember) -> None:
    if member.is_owner:
        raise Forbidden("The store owner cannot be changed or removed")


def change_role(
    db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID, role: Role
) -> StoreMember:
    if member_id == acting_member_id:
        raise BadRequest("You cannot change your own role")
    _lock_staff_changes(db, store_id, acting_member_id)
    member = get_member(db, store_id, member_id)
    _refuse_if_owner(member)
    if not member.active:
        raise Conflict("This person is inactive. Invite them again to bring them back.")
    member.role = role
    db.commit()
    return member


def set_alias(
    db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID, alias: str | None
) -> StoreMember:
    member = get_member(db, store_id, member_id)
    if member.id != acting_member_id:
        _refuse_if_owner(member)
    member.alias = alias
    db.commit()
    return member


def list_attendance(db: Session, store_id: UUID, member_id: UUID) -> list[Attendance]:
    member = get_member(db, store_id, member_id)
    return list(
        db.scalars(
            select(Attendance)
            .where(Attendance.store_id == store_id, Attendance.member_id == member.id)
            .order_by(Attendance.work_date.desc())
            .limit(ATTENDANCE_SHOWN)
        )
    )


def attendance_on(db: Session, store_id: UUID, work_date: date) -> list[Attendance]:
    return list(
        db.scalars(
            select(Attendance).where(
                Attendance.store_id == store_id, Attendance.work_date == work_date
            )
        )
    )


def record_attendance(
    db: Session,
    store_id: UUID,
    member_id: UUID,
    recorded_by: UUID,
    work_date: date,
    status: AttendanceStatus,
    note: str | None,
) -> Attendance:
    member = get_member(db, store_id, member_id)
    if not member.active:
        raise Conflict("This person is inactive, so attendance cannot be added.")
    if work_date > datetime.now(_STORE_TZ).date():
        raise Invalid("Attendance cannot be for a future date")
    statement = insert(Attendance).values(
        store_id=store_id,
        member_id=member.id,
        work_date=work_date,
        status=status,
        note=note,
        recorded_by_user_id=recorded_by,
    )
    row = db.scalars(
        statement.on_conflict_do_update(
            index_elements=[Attendance.member_id, Attendance.work_date],
            set_={
                "status": statement.excluded.status,
                "note": statement.excluded.note,
                "recorded_by_user_id": statement.excluded.recorded_by_user_id,
                "updated_at": func.now(),
            },
        ).returning(Attendance),
        execution_options={"populate_existing": True},
    ).one()
    db.commit()
    return row


def deactivate(db: Session, store_id: UUID, member_id: UUID, acting_member_id: UUID) -> StoreMember:
    """Turn off a member's access (takes effect on their next request). Commits.

    @raises BadRequest when deactivating yourself, so a store can't lock itself out
    """
    member = get_member(db, store_id, member_id)
    if member.id == acting_member_id:
        raise BadRequest("You cannot deactivate yourself")
    _lock_staff_changes(db, store_id, acting_member_id)
    _refuse_if_owner(member)
    member.active = False
    db.commit()
    return member
