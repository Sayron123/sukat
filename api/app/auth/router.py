"""Auth HTTP endpoints. Thin: read the request, call auth.service, shape the response."""

from fastapi import APIRouter, Request, status

from app.auth import service
from app.auth.deps import CurrentMemberDep, DbSession
from app.auth.rate_limit import client_ip
from app.auth.schemas import LoginIn, MeOut, SignupIn, TokenOut
from app.stores.models import Store

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: DbSession) -> TokenOut:
    """Create a store, its first user (manager), and return a token."""
    return service.signup(db, body)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: DbSession) -> TokenOut:
    """Email + password -> token. Rate-limited per email and per IP (429)."""
    return service.login(db, body.email, body.password, client_ip(request))


@router.get("/me", response_model=MeOut)
def me(current: CurrentMemberDep, db: DbSession) -> MeOut:
    store = db.get(Store, current.store_id)
    assert store is not None  # guaranteed by the membership foreign key
    return MeOut(
        user_id=current.user.id,
        email=current.user.email,
        full_name=current.user.full_name,
        store_id=store.id,
        store_name=store.name,
        role=current.role,
    )
