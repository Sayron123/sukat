"""Who is calling? Resolves the bearer token to an active store membership."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import decode_access_token
from app.core.db import get_db
from app.core.errors import Forbidden, Unauthorized
from app.stores.models import Role, StoreMember

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class CurrentMember:
    """The caller. store_id always comes from the verified token, never from the request."""

    user: User
    member_id: UUID
    store_id: UUID
    role: str
    is_owner: bool = False


def _unauthorized() -> Unauthorized:
    return Unauthorized("Not authenticated", headers={"WWW-Authenticate": "Bearer"})


def get_current_member(
    db: DbSession,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentMember:
    if creds is None:
        raise _unauthorized()
    data = decode_access_token(creds.credentials)
    if data is None:
        raise _unauthorized()

    # Re-check the membership on every request, so deactivation takes effect immediately.
    member = db.scalar(
        select(StoreMember).where(
            StoreMember.user_id == data.user_id,
            StoreMember.store_id == data.store_id,
            StoreMember.active.is_(True),
        )
    )
    if member is None or member.user.token_version != data.token_version:
        raise _unauthorized()
    return CurrentMember(
        user=member.user,
        member_id=member.id,
        store_id=member.store_id,
        role=member.role,
        is_owner=member.is_owner,
    )


CurrentMemberDep = Annotated[CurrentMember, Depends(get_current_member)]


class EmailNotVerified(Forbidden):
    code = "email_not_verified"


def email_confirmation(current: CurrentMember) -> bool:
    return current.is_owner and current.user.email_verified_at is None


def get_verified_member(current: CurrentMemberDep) -> CurrentMember:
    if email_confirmation(current):
        raise EmailNotVerified(
            "Confirm your email first. Check your inbox, or resend the link from the More tab."
        )
    return current


VerifiedMemberDep = Annotated[CurrentMember, Depends(get_verified_member)]


def require_role(*roles: str) -> Callable[[CurrentMember], CurrentMember]:
    """Dependency factory: allow only members whose role is in `roles`, else 403.

    Usage:
        @router.post("/x")
        def x(member: Annotated[CurrentMember, Depends(require_role("manager"))]): ...
    """
    allowed = {Role(r).value for r in roles}  # fails fast on a typo like "manger"
    if not allowed:
        raise ValueError("require_role needs at least one role")

    def _check(member: CurrentMemberDep) -> CurrentMember:
        if member.role not in allowed:
            raise Forbidden("You do not have permission to do this")
        return member

    return _check
