"""Who is calling? Resolves the bearer token to an active store membership."""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import User
from app.auth.security import decode_access_token
from app.core.db import get_db
from app.stores.models import StoreMember

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class CurrentMember:
    """The caller. store_id always comes from the verified token, never from the request."""

    user: User
    member_id: UUID
    store_id: UUID
    role: str


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
    if member is None:
        raise _unauthorized()
    return CurrentMember(
        user=member.user, member_id=member.id, store_id=member.store_id, role=member.role
    )


CurrentMemberDep = Annotated[CurrentMember, Depends(get_current_member)]
