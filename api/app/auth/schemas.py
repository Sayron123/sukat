import re
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, EmailStr, Field, field_validator, model_validator

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

USERNAME_RULES = "Use 3 to 30 small letters, numbers, dots or underscores, starting with a letter."
_USERNAME = re.compile(r"^[a-z][a-z0-9._]{2,29}$")


def clean_username(value: str) -> str:
    value = value.strip().lower()
    if not _USERNAME.fullmatch(value):
        raise ValueError(USERNAME_RULES)
    return value


def clean_login(value: str) -> str:
    return value.strip().lower()


LinkToken = Annotated[str, Field(max_length=200)]

TERMS_VERSION = "2026-11-15"


def must_accept_terms(accepted: bool) -> bool:
    if not accepted:
        raise ValueError("Please agree to the Terms and Privacy Policy")
    return accepted


def _normalize_email(v: str) -> str:
    return v.strip().lower()


def _not_blank(v: str) -> str:
    v = v.strip()
    if not v:
        raise ValueError("must not be blank")
    return v


class SignupIn(BaseModel):
    store_name: str = Field(min_length=1, max_length=120)
    store_address: str | None = Field(default=None, max_length=300)
    full_name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: NewPassword
    accept_terms: bool = Field(default=False, validate_default=True)

    _norm = field_validator("email")(_normalize_email)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        return must_accept_terms(v)

    _strip = field_validator("store_name", "full_name")(_not_blank)

    @field_validator("store_address")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        """The address is optional: a blank one (empty form field) is saved as no address."""
        return (v.strip() or None) if v is not None else None


class LoginIn(BaseModel):
    login: str | None = Field(default=None, max_length=320)
    email: str | None = Field(default=None, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _one_login(self) -> "LoginIn":
        value = clean_login(self.login or self.email or "")
        if not value:
            raise ValueError("Enter your email or username")
        self.login = value
        return self


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: NewPassword


class ProfileIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=120)

    _strip = field_validator("full_name")(_not_blank)


class ForgotPasswordIn(BaseModel):
    email: EmailStr

    _norm = field_validator("email")(_normalize_email)


class ResetPasswordIn(BaseModel):
    token: LinkToken
    new_password: NewPassword


class VerifyEmailIn(BaseModel):
    token: LinkToken


class GoogleIn(BaseModel):
    code: str = Field(min_length=1, max_length=2000)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str = Field(min_length=1, max_length=300)
    nonce: str = Field(min_length=16, max_length=200)


GoogleTicket = Annotated[str, Field(min_length=1, max_length=2000)]


class GoogleTicketOut(BaseModel):
    ticket: str
    email: str
    name: str
    account: bool


class GoogleSignupIn(BaseModel):
    ticket: GoogleTicket
    full_name: str = Field(min_length=1, max_length=120)
    store_name: str = Field(min_length=1, max_length=120)
    store_address: str | None = Field(default=None, max_length=300)
    accept_terms: bool = Field(default=False, validate_default=True)

    _strip = field_validator("store_name", "full_name")(_not_blank)

    @field_validator("accept_terms")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        return must_accept_terms(v)

    @field_validator("store_address")
    @classmethod
    def _strip_optional(cls, v: str | None) -> str | None:
        return (v.strip() or None) if v is not None else None


class GoogleClientOut(BaseModel):
    client_id: str | None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class MeOut(BaseModel):
    user_id: UUID
    email: str | None
    username: str | None
    full_name: str
    email_verified: bool
    email_confirmation: bool
    google: bool
    google_email: str | None
    store_id: UUID
    store_name: str
    store_address: str | None
    role: str
