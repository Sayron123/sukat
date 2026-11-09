from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, created_at_col, updated_at_col, uuid_pk


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("email = lower(email)", name="email_lowercase"),)

    id: Mapped[UUID] = uuid_pk()
    # Always stored lowercase (normalized in code), so the unique constraint is case-insensitive.
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    # When the person agreed to the Terms and Privacy Policy, and which version. Set at
    # signup; empty for accounts made before 0010 and for staff who joined by invite.
    terms_accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    terms_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class AuthFailure(Base):
    """One failed login/accept attempt for a key ("email:..." or "ip:..."). Used for rate
    limiting; rows older than AUTH_FAILURE_WINDOW_MINUTES are deleted automatically."""

    __tablename__ = "auth_failures"
    __table_args__ = (Index("ix_auth_failures_key_created_at", "key", "created_at"),)

    id: Mapped[UUID] = uuid_pk()
    key: Mapped[str] = mapped_column(String(400), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
