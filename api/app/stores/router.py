"""Staff HTTP endpoints. Thin: check the role, call stores.service, shape the response."""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from app.auth.deps import CurrentMember, CurrentMemberDep, DbSession, require_role
from app.auth.rate_limit import client_ip
from app.auth.schemas import TokenOut
from app.stores import service
from app.stores.models import Attendance, AttendanceStatus, Role, StoreMember
from app.stores.schemas import (
    AcceptInviteIn,
    AliasIn,
    AttendanceIn,
    AttendanceOut,
    DayAttendanceOut,
    InviteIn,
    InviteOut,
    InvitePreviewIn,
    InvitePreviewOut,
    RoleIn,
    StaffOut,
)

router = APIRouter(tags=["staff"])

Manager = Annotated[CurrentMember, Depends(require_role(Role.MANAGER))]
ManagerOrSecretary = Annotated[CurrentMember, Depends(require_role(Role.MANAGER, Role.SECRETARY))]


def staff_out(m: StoreMember, *, show_email: bool = True) -> StaffOut:
    return StaffOut(
        member_id=m.id,
        user_id=m.user_id,
        email=m.user.email if show_email else None,
        full_name=m.user.full_name,
        alias=m.alias,
        role=Role(m.role),
        active=m.active,
        is_owner=m.is_owner,
        created_at=m.created_at,
    )


def attendance_out(row: Attendance) -> AttendanceOut:
    return AttendanceOut(
        id=row.id,
        work_date=row.work_date,
        status=AttendanceStatus(row.status),
        note=row.note,
        updated_at=row.updated_at,
    )


@router.post("/staff/invites", response_model=InviteOut, status_code=status.HTTP_201_CREATED)
def invite_staff(body: InviteIn, current: ManagerOrSecretary, db: DbSession) -> InviteOut:
    """Invite someone by email. The token is returned once; share it with the invitee."""
    row, token = service.invite(
        db, current.store_id, current.user.id, current.role, body.email, body.role
    )
    return InviteOut(
        id=row.id, email=row.email, role=Role(row.role), expires_at=row.expires_at, token=token
    )


@router.post("/staff/invites/preview", response_model=InvitePreviewOut)
def preview_invite(body: InvitePreviewIn, request: Request, db: DbSession) -> InvitePreviewOut:
    return service.preview_invite(db, body.token, client_ip(request))


@router.post("/staff/invites/accept", response_model=TokenOut)
def accept_invite(body: AcceptInviteIn, request: Request, db: DbSession) -> TokenOut:
    """Join a store with an invite token (no login needed)."""
    return service.accept_invite(db, body.token, body.password, body.full_name, client_ip(request))


@router.get("/staff", response_model=list[StaffOut])
def list_staff(current: CurrentMemberDep, db: DbSession) -> list[StaffOut]:
    show_email = current.role != Role.MEMBER
    return [staff_out(m, show_email=show_email) for m in service.list_members(db, current.store_id)]


@router.get("/staff/{member_id}", response_model=StaffOut)
def get_staff(member_id: UUID, current: ManagerOrSecretary, db: DbSession) -> StaffOut:
    return staff_out(service.get_member(db, current.store_id, member_id))


@router.patch("/staff/{member_id}/role", response_model=StaffOut)
def change_staff_role(member_id: UUID, body: RoleIn, current: Manager, db: DbSession) -> StaffOut:
    return staff_out(
        service.change_role(db, current.store_id, member_id, current.member_id, body.role)
    )


@router.patch("/staff/{member_id}/alias", response_model=StaffOut)
def change_staff_alias(member_id: UUID, body: AliasIn, current: Manager, db: DbSession) -> StaffOut:
    return staff_out(
        service.set_alias(db, current.store_id, member_id, current.member_id, body.alias)
    )


@router.get("/attendance", response_model=list[DayAttendanceOut])
def list_store_attendance(
    start: date, end: date, current: ManagerOrSecretary, db: DbSession
) -> list[DayAttendanceOut]:
    return [
        DayAttendanceOut(member_id=r.member_id, **attendance_out(r).model_dump())
        for r in service.attendance_between(db, current.store_id, start, end)
    ]


@router.get("/staff/{member_id}/attendance", response_model=list[AttendanceOut])
def list_staff_attendance(
    member_id: UUID, current: ManagerOrSecretary, db: DbSession
) -> list[AttendanceOut]:
    return [attendance_out(r) for r in service.list_attendance(db, current.store_id, member_id)]


@router.post("/staff/{member_id}/attendance", response_model=AttendanceOut)
def record_staff_attendance(
    member_id: UUID, body: AttendanceIn, current: ManagerOrSecretary, db: DbSession
) -> AttendanceOut:
    return attendance_out(
        service.record_attendance(
            db,
            current.store_id,
            member_id,
            current.user.id,
            body.work_date,
            body.status,
            body.note,
        )
    )


@router.post("/staff/{member_id}/deactivate", response_model=StaffOut)
def deactivate_staff(member_id: UUID, current: Manager, db: DbSession) -> StaffOut:
    return staff_out(service.deactivate(db, current.store_id, member_id, current.member_id))
