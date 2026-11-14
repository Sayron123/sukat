"""Staff and invites. Every function is scoped to one store; raises AppError subclasses."""

import secrets
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
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
from app.auth.service import issue_token, user_by_login
from app.core.config import settings
from app.core.errors import BadRequest, Conflict, Forbidden, Invalid, NotFound, Unauthorized
from app.stores.models import Attendance, AttendanceStatus, Invite, Role, Store, StoreMember
from app.stores.schemas import AcceptInviteIn, InvitePreviewOut

_STORE_TZ = ZoneInfo(settings.STORE_TIMEZONE)
ATTENDANCE_SHOWN = 31
ATTENDANCE_RANGE_DAYS = 62
USERNAME_TAKEN = "That username is taken. Try another one."


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


def update_store(db: Session, store_id: UUID, name: str, address: str | None) -> Store:
    store = db.get(Store, store_id)
    if store is None:
        raise NotFound("Store not found")
    store.name = name
    store.address = address
    db.commit()
    return store


def list_members(db: Session, store_id: UUID) -> list[StoreMember]:
    return list(
        db.scalars(
            select(StoreMember)
            .where(StoreMember.store_id == store_id)
            .order_by(StoreMember.created_at, StoreMember.id)
        )
    )


def pending_invites(db: Session, store_id: UUID) -> list[Invite]:
    return list(
        db.scalars(
            select(Invite)
            .where(
                Invite.store_id == store_id,
                Invite.accepted_at.is_(None),
                Invite.expires_at > datetime.now(UTC),
            )
            .order_by(Invite.created_at.desc(), Invite.id)
        )
    )


def _invite_hours(role: str) -> int:
    return (
        settings.MANAGER_INVITE_EXPIRE_HOURS
        if role == Role.MANAGER
        else settings.INVITE_EXPIRE_HOURS
    )


def invite(
    db: Session, store_id: UUID, invited_by: UUID, inviter_role: str, role: Role, name: str | None
) -> tuple[Invite, str]:
    """Create an invite link and return it with the raw token (shown once; only its hash
    is stored). `name` is only a label so staff can tell open invites apart. Commits.

    @raises Forbidden when a secretary invites anyone but a member
    """
    if inviter_role == Role.SECRETARY and role != Role.MEMBER:
        raise Forbidden("Secretaries can only invite members")
    token = secrets.token_urlsafe(32)
    row = Invite(
        store_id=store_id,
        name=name,
        role=role,
        token_hash=hash_token(token),
        invited_by_user_id=invited_by,
        expires_at=datetime.now(UTC) + timedelta(hours=_invite_hours(role)),
    )
    db.add(row)
    db.commit()
    return row, token


def renew_invite(
    db: Session, store_id: UUID, invite_id: UUID, renewed_by: UUID, renewer_role: str
) -> tuple[Invite, str]:
    row = db.scalar(
        select(Invite)
        .where(Invite.id == invite_id, Invite.store_id == store_id, Invite.accepted_at.is_(None))
        .with_for_update()
    )
    if row is None:
        raise NotFound("Invite not found")
    if renewer_role == Role.SECRETARY and row.role != Role.MEMBER:
        raise Forbidden("Secretaries can only invite members")
    token = secrets.token_urlsafe(32)
    row.token_hash = hash_token(token)
    row.invited_by_user_id = renewed_by
    row.expires_at = datetime.now(UTC) + timedelta(hours=_invite_hours(row.role))
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
    return InvitePreviewOut(store_name=store.name, role=Role(row.role), name=row.name)


def _new_account(db: Session, username: str, full_name: str, password: str) -> User:
    if not password_is_strong(password):
        raise Invalid(PASSWORD_RULES_MESSAGE)
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise Conflict(USERNAME_TAKEN)
    user = User(username=username, full_name=full_name, password_hash=hash_password(password))
    db.add(user)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError:
        raise Conflict(USERNAME_TAKEN) from None
    return user


def _existing_account(db: Session, login: str, password: str, ip: str | None) -> User:
    limits = limits_for(login, ip)
    ensure_not_limited(db, limits)
    user = user_by_login(db, login)
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok:
        record_failure(db, [key for key, _ in limits])
        raise Unauthorized("Incorrect email, username or password")
    clear_failures(db, email_key(login))
    return user


def accept_invite(db: Session, body: AcceptInviteIn, ip: str | None) -> TokenOut:
    """Join a store with an invite link and return a token for that store. Commits.

    New person: picks a username, their name and a password that meets the rules.
    Existing account: signs in with its email or username and password. A deactivated
    member is re-activated with the invite's role, but only from a manager's invite.
    Bad tokens count against the IP; wrong passwords against the login too.

    @raises BadRequest (invalid/expired), Unauthorized (wrong password), Invalid (weak
        password), Conflict (username taken, already active staff), Forbidden (a
        secretary's invite can't bring back a removed person), TooManyRequests
    """
    row = _open_invite(db, body.token, ip, lock=True)
    if body.username is not None:
        assert body.full_name is not None
        user = _new_account(db, body.username, body.full_name, body.password)
    else:
        assert body.login is not None
        user = _existing_account(db, body.login, body.password, ip)

    member = db.scalar(
        select(StoreMember).where(
            StoreMember.store_id == row.store_id, StoreMember.user_id == user.id
        )
    )
    if member is None:
        db.add(StoreMember(store_id=row.store_id, user_id=user.id, role=row.role))
    elif member.active:
        raise Conflict("You are already staff in this store")
    elif not _inviter_is_still_manager(db, row, lock=False):
        raise Forbidden("You were removed from this store. Ask a manager for a new invite.")
    else:
        member.active = True  # a re-invite brings a deactivated person back
        member.role = row.role

    user.terms_accepted_at = datetime.now(UTC)
    user.terms_version = TERMS_VERSION
    row.accepted_at = datetime.now(UTC)
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


def attendance_between(db: Session, store_id: UUID, start: date, end: date) -> list[Attendance]:
    if end < start:
        raise Invalid("The end date is before the start date")
    if (end - start).days >= ATTENDANCE_RANGE_DAYS:
        raise Invalid(f"Ask for at most {ATTENDANCE_RANGE_DAYS} days at a time")
    return list(
        db.scalars(
            select(Attendance)
            .where(
                Attendance.store_id == store_id,
                Attendance.work_date >= start,
                Attendance.work_date <= end,
            )
            .order_by(Attendance.work_date)
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
