from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.stores.models import Role


class InviteIn(BaseModel):
    email: EmailStr
    role: Role = Role.MEMBER

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return v.strip().lower()


class InviteOut(BaseModel):
    id: UUID
    email: str
    role: Role
    expires_at: datetime
    # The raw token. Shown ONCE here; only its hash is stored. Send it to the invitee.
    token: str


class AcceptInviteIn(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    # Needed only when the invitee does not have an account yet.
    full_name: str | None = Field(default=None, max_length=120)
    password: str = Field(min_length=8, max_length=128)


class StaffOut(BaseModel):
    member_id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: Role
    active: bool
    created_at: datetime
