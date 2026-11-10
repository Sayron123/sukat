from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "store_members",
        sa.Column("is_owner", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.execute(
        """
        UPDATE store_members AS m
        SET is_owner = true
        FROM (
            SELECT DISTINCT ON (store_id) id
            FROM store_members
            WHERE role = 'manager' AND active
            ORDER BY store_id, created_at, id
        ) AS first_manager
        WHERE m.id = first_manager.id
        """
    )
    op.create_index(
        "uq_store_members_one_owner",
        "store_members",
        ["store_id"],
        unique=True,
        postgresql_where=sa.text("is_owner"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_store_members_one_owner",
        table_name="store_members",
        postgresql_where=sa.text("is_owner"),
    )
    op.drop_column("store_members", "is_owner")
