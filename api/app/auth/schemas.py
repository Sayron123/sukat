from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

# Version of the Terms and Privacy Policy (web/src/app/terms, web/src/app/privacy) that a
# new account agrees to. Change it together with the pages' "Last updated" date.
TERMS_VERSION = "2026-11-09"


def _normalize_email(v: str) -> str:
    return v.strip().lower()


class SignupIn(BaseModel):
    store_name: str = Field(min_length=1, max_length=120)
    store_address: str | None = Field(default=None, max_length=300)
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # Must be true: the person agreed to the Terms and Privacy Policy on the signup form.
    accept_terms: bool = Field(default=False, validate_default=True)

    _norm = field_validator("email")(_normalize_email)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Please agree to the Terms and Privacy Policy")
        return v

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


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: UUID
    email: str
    full_name: str
    store_id: UUID
    store_name: str
    store_address: str | None
    role: str
