from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.schemas import must_accept_terms
from app.stores.models import AttendanceStatus, Role


def _blank_to_none(value: str | None) -> str | None:
    return (value or "").strip() or None


class InviteIn(BaseModel):
    email: EmailStr
    role: Role

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower()


class RoleIn(BaseModel):
    role: Role


class AliasIn(BaseModel):
    alias: str | None = Field(max_length=120)

    @field_validator("alias")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class AttendanceIn(BaseModel):
    work_date: date
    status: AttendanceStatus
    note: str | None = Field(default=None, max_length=300)

    @field_validator("note")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class AttendanceOut(BaseModel):
    id: UUID
    work_date: date
    status: AttendanceStatus
    note: str | None
    updated_at: datetime


class InviteOut(BaseModel):
    id: UUID
    email: str
    role: Role
    expires_at: datetime
    # The raw token. Shown ONCE here; only its hash is stored. Send it to the invitee.
    token: str


class InvitePreviewIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InvitePreviewOut(BaseModel):
    store_name: str
    role: Role
    email: str
    has_account: bool


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        return must_accept_terms(v)


class StaffOut(BaseModel):
    member_id: UUID
    user_id: UUID
    email: str | None
    full_name: str
    alias: str | None
    role: Role
    active: bool
    is_owner: bool
    created_at: datetime
