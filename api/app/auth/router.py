from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth.deps import CurrentMemberDep, DbSession
from app.auth.models import User
from app.auth.schemas import LoginIn, MeOut, SignupIn, TokenOut
from app.auth.security import create_access_token, hash_password, verify_password
from app.stores.models import Role, Store, StoreMember

router = APIRouter(prefix="/auth", tags=["auth"])

EMAIL_TAKEN = "An account with this email already exists"


@router.post("/signup", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def signup(body: SignupIn, db: DbSession) -> TokenOut:
    """Create a store, its first user, and a manager membership in ONE transaction."""
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)

    store = Store(name=body.store_name)
    user = User(
        email=body.email, full_name=body.full_name, password_hash=hash_password(body.password)
    )
    db.add_all([store, user])
    db.flush()  # assigns ids, still inside the same transaction
    db.add(StoreMember(store_id=store.id, user_id=user.id, role=Role.MANAGER))
    try:
        db.commit()  # all three rows are saved together, or none are
    except IntegrityError as e:
        db.rollback()
        # Two signups with the same email at the same moment: the unique constraint catches it.
        if getattr(getattr(e.orig, "diag", None), "constraint_name", None) == "uq_users_email":
            raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from None
        raise

    token, expires_in = create_access_token(user.id, store.id)
    return TokenOut(access_token=token, expires_in=expires_in)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: DbSession) -> TokenOut:
    user = db.scalar(select(User).where(User.email == body.email))
    # Always run the hash check (even for unknown emails) so timing does not reveal accounts.
    password_ok = verify_password(body.password, user.password_hash if user else None)
    if user is None or not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    # Phase 1: a user signs in to their first active store. Store switching comes later.
    member = db.scalar(
        select(StoreMember)
        .where(StoreMember.user_id == user.id, StoreMember.active.is_(True))
        .order_by(StoreMember.created_at, StoreMember.id)
        .limit(1)
    )
    if member is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Your account is not active in any store")

    token, expires_in = create_access_token(user.id, member.store_id)
    return TokenOut(access_token=token, expires_in=expires_in)


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
