"""ai provider log and per-store monthly budget.

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-09 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_usage",
        sa.Column("provider", sa.String(length=20), server_default="anthropic", nullable=False),
    )
    op.alter_column("ai_usage", "provider", server_default=None)
    op.add_column("stores", sa.Column("ai_monthly_budget_centavos", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_stores_ai_budget_not_negative"), "stores", "ai_monthly_budget_centavos >= 0"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_stores_ai_budget_not_negative"), "stores", type_="check")
    op.drop_column("stores", "ai_monthly_budget_centavos")
    op.drop_column("ai_usage", "provider")
