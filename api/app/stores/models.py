from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    false,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.auth.models import User
from app.core.base import Base, created_at_col, updated_at_col, uuid_pk


class Role(StrEnum):
    MANAGER = "manager"
    SECRETARY = "secretary"
    MEMBER = "member"


ROLE_CHECK = "role IN ('manager', 'secretary', 'member')"


class AttendanceStatus(StrEnum):
    PRESENT = "present"
    LATE = "late"
    HALF_DAY = "half_day"
    ABSENT = "absent"


ATTENDANCE_STATUS_CHECK = "status IN ('present', 'late', 'half_day', 'absent')"


class Store(Base):
    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint("ai_monthly_budget_centavos >= 0", name="ai_budget_not_negative"),
    )

    id: Mapped[UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ai_monthly_budget_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class StoreMember(Base):
    """Links a user to a store with a role. One row per (store, user)."""

    __tablename__ = "store_members"
    __table_args__ = (
        UniqueConstraint("store_id", "user_id"),
        CheckConstraint(ROLE_CHECK, name="role"),
        Index(
            "uq_store_members_one_owner",
            "store_id",
            unique=True,
            postgresql_where=text("is_owner"),
        ),
    )

    id: Mapped[UUID] = uuid_pk()
    # No separate index on store_id: the (store_id, user_id) unique constraint covers it.
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())
    is_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()

    user: Mapped[User] = relationship(lazy="joined")


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("member_id", "work_date"),
        CheckConstraint(ATTENDANCE_STATUS_CHECK, name="status"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    member_id: Mapped[UUID] = mapped_column(
        ForeignKey("store_members.id", ondelete="RESTRICT"), nullable=False
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = created_at_col()
    updated_at: Mapped[datetime] = updated_at_col()


class Invite(Base):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK, name="role"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    # SHA-256 of the invite token. The raw token is only shown once, when the invite is created.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    invited_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = created_at_col()
