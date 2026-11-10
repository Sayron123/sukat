"""Auth HTTP endpoints. Thin: read the request, call auth.service, shape the response."""

from fastapi import APIRouter, Request, status

from app.auth import service
from app.auth.deps import CurrentMemberDep, DbSession
from app.auth.rate_limit import client_ip
from app.auth.schemas import (
    ChangePasswordIn,
    ForgotPasswordIn,
    LoginIn,
    MeOut,
    ProfileIn,
    ResetPasswordIn,
    SignupIn,
    TokenOut,
    VerifyEmailIn,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, request: Request, db: DbSession) -> TokenOut:
    """Create a store, its first user (manager), and return a token."""
    return service.signup(db, body, client_ip(request))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DbSession) -> TokenOut:
    """Email + password -> token. Rate-limited per email and per IP (429)."""
    return service.login(db, body.email, body.password, client_ip(request))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current: CurrentMemberDep, db: DbSession) -> None:
    service.logout(db, current.user)


@router.post("/change-password", response_model=TokenOut)
def change_password(
    body: ChangePasswordIn, request: Request, current: CurrentMemberDep, db: DbSession
) -> TokenOut:
    return service.change_password(
        db,
        current.user,
        current.store_id,
        body.current_password,
        body.new_password,
        client_ip(request),
    )


@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(body: ForgotPasswordIn, request: Request, db: DbSession) -> None:
    service.request_password_reset(db, body.email, client_ip(request))


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordIn, request: Request, db: DbSession) -> None:
    service.reset_password(db, body.token, body.new_password, client_ip(request))


@router.post("/verify-email", status_code=status.HTTP_204_NO_CONTENT)
def verify_email(body: VerifyEmailIn, request: Request, db: DbSession) -> None:
    service.verify_email(db, body.token, client_ip(request))


@router.post("/resend-verification", status_code=status.HTTP_204_NO_CONTENT)
def resend_verification(request: Request, current: CurrentMemberDep, db: DbSession) -> None:
    service.resend_verification(db, current.user, client_ip(request))


@router.get("/me", response_model=MeOut)
def me(current: CurrentMemberDep, db: DbSession) -> MeOut:
    return service.get_me(db, current)


@router.patch("/me", response_model=MeOut)
def update_me(body: ProfileIn, current: CurrentMemberDep, db: DbSession) -> MeOut:
    return service.update_profile(db, current, body.full_name)
