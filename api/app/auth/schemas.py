import re
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator

PASSWORD_RULES_MESSAGE = (
    "Use at least 8 characters with a capital letter, a small letter, a number and a symbol."
)
_PASSWORD_RULES = (r"[A-Z]", r"[a-z]", r"[0-9]", r"[^A-Za-z0-9\s]")


def password_is_strong(value: str) -> bool:
    return len(value) >= 8 and all(re.search(rule, value) for rule in _PASSWORD_RULES)


def _strong_password(value: str) -> str:
    if not password_is_strong(value):
        raise ValueError(PASSWORD_RULES_MESSAGE)
    return value


NewPassword = Annotated[str, Field(min_length=8, max_length=128), AfterValidator(_strong_password)]
LinkToken = Annotated[str, Field(max_length=200)]


def _normalize_email(v: str) -> str:
    return v.strip().lower()


class SignupIn(BaseModel):
    store_name: str = Field(min_length=1, max_length=120)
    store_address: str | None = Field(default=None, max_length=300)
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: NewPassword

    _norm = field_validator("email")(_normalize_email)

    @field_validator("store_name", "full_name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("store_address")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        """The address is optional: a blank one (empty form field) is saved as no address."""
        return (v.strip() or None) if v is not None else None


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    _norm = field_validator("email")(_normalize_email)


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: NewPassword


class ForgotPasswordIn(BaseModel):
    email: EmailStr

    _norm = field_validator("email")(_normalize_email)


class ResetPasswordIn(BaseModel):
    token: LinkToken
    new_password: NewPassword


class VerifyEmailIn(BaseModel):
    token: LinkToken


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    email_verified: bool
    store_id: UUID
    store_name: str
    store_address: str | None
    role: str
