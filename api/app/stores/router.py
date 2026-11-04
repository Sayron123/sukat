"""Staff management. Every query is scoped to the caller's store_id from the token."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select

from app.auth.deps import CurrentMember, DbSession, require_role
from app.auth.models import User
from app.auth.schemas import TokenOut
from app.auth.security import create_access_token, hash_password, verify_password
from app.core.config import settings
from app.stores.models import Invite, Role, StoreMember
from app.stores.schemas import AcceptInviteIn, InviteIn, InviteOut, StaffOut

router = APIRouter(tags=["staff"])

Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]
ManagerOrSecretary = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _staff_out(m: StoreMember) -> StaffOut:
    return StaffOut(
        member_id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        role=Role(m.role),
        active=m.active,
        created_at=m.created_at,
    )


def _get_member_in_store(db: DbSession, store_id: UUID, member_id: UUID) -> StoreMember:
    """Find a member of THIS store. Another store's member is reported as 404 (not 403),
    so callers cannot even learn that it exists."""
    member = db.scalar(
        select(StoreMember).where(StoreMember.id == member_id, StoreMember.store_id == store_id)
    )
    if member is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Staff member not found")
    return member


@router.post("/staff/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_staff(body: InviteIn, current: Manager, db: DbSession) -> InviteOut:
    already_active = db.scalar(
        select(StoreMember.id)
        .join(User, User.id == StoreMember.user_id)
        .where(
            StoreMember.store_id == current.store_id,
            StoreMember.active.is_(True),
            User.email == body.email,
        )
    )
    if already_active is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This person is already active staff")

    # Only one open invite per email per store: replace any older unaccepted one.
    db.execute(
        delete(Invite).where(
            Invite.store_id == current.store_id,
            Invite.email == body.email,
            Invite.accepted_at.is_(None),
        )
    )
    token = secrets.token_urlsafe(32)
    invite = Invite(
        store_id=current.store_id,
        email=body.email,
        role=body.role,
        token_hash=_hash_token(token),
        invited_by_user_id=current.user.id,
        expires_at=datetime.now(UTC) + timedelta(hours=settings.INVITE_EXPIRE_HOURS),
    )
    db.add(invite)
    db.commit()
    return InviteOut(
        id=invite.id,
        email=invite.email,
        role=Role(invite.role),
        expires_at=invite.expires_at,
        token=token,
    )


@router.post("/invites/accept", response_model=TokenOut)
def accept_invite(body: AcceptInviteIn, db: DbSession) -> TokenOut:
    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "This invite is invalid or has expired")
    # FOR UPDATE locks the invite row, so the same invite cannot be accepted twice at once.
    invite = db.scalar(
        select(Invite).where(Invite.token_hash == _hash_token(body.token)).with_for_update()
    )
    if invite is None or invite.accepted_at is not None or invite.expires_at <= datetime.now(UTC):
        raise invalid

    user = db.scalar(select(User).where(User.email == invite.email))
    if user is None:
        if not body.full_name or not body.full_name.strip():
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "full_name is required")
        user = User(
            email=invite.email,
            full_name=body.full_name.strip(),
            password_hash=hash_password(body.password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(body.password, user.password_hash):
        # Existing account: the invitee proves it is theirs with their current password.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect password for this account")

    member = db.scalar(
        select(StoreMember).where(
            StoreMember.store_id == invite.store_id, StoreMember.user_id == user.id
        )
    )
    if member is None:
        db.add(StoreMember(store_id=invite.store_id, user_id=user.id, role=invite.role))
    elif member.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "You are already staff in this store")
    else:
        member.active = True  # a re-invite brings a deactivated person back
        member.role = invite.role

    invite.accepted_at = datetime.now(UTC)
    db.commit()

    token, expires_in = create_access_token(user.id, invite.store_id)
    return TokenOut(access_token=token, expires_in=expires_in)


@router.get("/staff", response_model=list[StaffOut])
def list_staff(current: ManagerOrSecretary, db: DbSession) -> list[StaffOut]:
    members = db.scalars(
        select(StoreMember)
        .where(StoreMember.store_id == current.store_id)
        .order_by(StoreMember.created_at, StoreMember.id)
    ).all()
    return [_staff_out(m) for m in members]


@router.get("/staff/{member_id}", response_model=StaffOut)
def get_staff(member_id: UUID, current: ManagerOrSecretary, db: DbSession) -> StaffOut:
    return _staff_out(_get_member_in_store(db, current.store_id, member_id))


@router.post("/staff/{member_id}/deactivate", response_model=StaffOut)
def deactivate_staff(member_id: UUID, current: Manager, db: DbSession) -> StaffOut:
    member = _get_member_in_store(db, current.store_id, member_id)
    if member.id == current.member_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    member.active = False
    db.commit()
    return _staff_out(member)
