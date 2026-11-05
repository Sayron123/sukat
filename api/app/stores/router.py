"""Staff HTTP endpoints. Thin: check the role, call stores.service, shape the response."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.auth.deps import CurrentMember, DbSession, require_role
from app.auth.rate_limit import client_ip
from app.auth.schemas import TokenOut
from app.stores import service
from app.stores.models import Role, StoreMember
from app.stores.schemas import AcceptInviteIn, InviteIn, InviteOut, StaffOut

router = APIRouter(tags=["staff"])

Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]
ManagerOrSecretary = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]


def staff_out(m: StoreMember) -> StaffOut:
    return StaffOut(
        member_id=m.id,
        user_id=m.user_id,
        email=m.user.email,
        full_name=m.user.full_name,
        role=Role(m.role),
        active=m.active,
        created_at=m.created_at,
    )


@router.post("/staff/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_staff(body: InviteIn, current: Manager, db: DbSession) -> InviteOut:
    """Invite someone by email. The token is returned once; share it with the invitee."""
    row, token = service.invite(db, current.store_id, current.user.id, body.email, body.role)
    return InviteOut(
        id=row.id, email=row.email, role=Role(row.role), expires_at=row.expires_at, token=token
    )


@router.post("/invites/accept", response_model=TokenOut)
def accept_invite(body: AcceptInviteIn, request: Request, db: DbSession) -> TokenOut:
    """Join a store with an invite token (no login needed)."""
    return service.accept_invite(db, body.token, body.password, body.full_name, client_ip(request))


@router.get("/staff", response_model=list[StaffOut])
def list_staff(current: ManagerOrSecretary, db: DbSession) -> list[StaffOut]:
    return [staff_out(m) for m in service.list_members(db, current.store_id)]


@router.get("/staff/{member_id}", response_model=StaffOut)
def get_staff(member_id: UUID, current: ManagerOrSecretary, db: DbSession) -> StaffOut:
    return staff_out(service.get_member(db, current.store_id, member_id))


@router.post("/staff/{member_id}/deactivate", response_model=StaffOut)
def deactivate_staff(member_id: UUID, current: Manager, db: DbSession) -> StaffOut:
    return staff_out(service.deactivate(db, current.store_id, member_id, current.member_id))
