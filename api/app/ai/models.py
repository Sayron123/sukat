from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base import Base, created_at_col, uuid_pk


class AIUsage(Base):
    """One AI call: who paid for it, which model, how many tokens, what it cost."""

    __tablename__ = "ai_usage"
    __table_args__ = (Index("ix_ai_usage_store_id_created_at", "store_id", "created_at"),)

    id: Mapped[UUID] = uuid_pk()
    store_id: Mapped[UUID] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    feature: Mapped[str] = mapped_column(String(40), nullable=False)  # e.g. "scan_read"
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False)
    # Fractions of a centavo: one scan can cost well under ₱1, so 4 decimals.
    cost_centavos: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    created_at: Mapped[datetime] = created_at_col()
