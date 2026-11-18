from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.auth.schemas import GoogleTicket, clean_login, clean_username, must_accept_terms
from app.stores.models import AttendanceStatus, Role


def _blank_to_none(value: str | None) -> str | None:
    return (value or "").strip() or None


class InviteIn(BaseModel):
    role: Role
    name: str | None = Field(default=None, max_length=60)

    _name = field_validator("name")(_blank_to_none)


class StoreIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    address: str | None = Field(max_length=300)

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("address")
    @classmethod
    def _address(cls, v: str | None) -> str | None:
        return _blank_to_none(v)


class StoreOut(BaseModel):
    name: str
    address: str | None


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


class DayAttendanceOut(AttendanceOut):
    member_id: UUID


class PendingInviteOut(BaseModel):
    id: UUID
    name: str | None
    role: Role
    created_at: datetime
    expires_at: datetime


class InviteOut(BaseModel):
    id: UUID
    name: str | None
    role: Role
    expires_at: datetime
    # The raw token. Shown ONCE here; only its hash is stored. Send it to the invitee.
    token: str


class InvitePreviewIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InvitePreviewOut(BaseModel):
    store_name: str
    role: Role
    name: str | None


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    username: str | None = Field(default=None, max_length=30)
    full_name: str | None = Field(default=None, max_length=120)
    login: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        return must_accept_terms(v)

    @model_validator(mode="after")
    def _new_or_existing(self) -> "AcceptInviteIn":
        if (self.username is None) == (self.login is None):
            raise ValueError("Choose a new username, or sign in with your existing account")
        if self.username is not None:
            self.username = clean_username(self.username)
            self.full_name = _blank_to_none(self.full_name)
            if self.full_name is None:
                raise ValueError("Enter your name")
        else:
            self.login = clean_login(self.login or "")
        return self


class AcceptGoogleIn(BaseModel):
    ticket: GoogleTicket
    token: str = Field(min_length=1, max_length=200)
    full_name: str | None = Field(default=None, max_length=120)
    accept_terms: bool = Field(default=False, validate_default=True)

    @field_validator("full_name")
    @classmethod
    def _optional_name(cls, v: str | None) -> str | None:
        return _blank_to_none(v)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        return must_accept_terms(v)


class StaffResetOut(BaseModel):
    token: str
    expires_at: datetime


class StaffOut(BaseModel):
    member_id: UUID
    user_id: UUID
    email: str | None
    username: str | None
    full_name: str
    alias: str | None
    role: Role
    active: bool
    is_owner: bool
    created_at: datetime
