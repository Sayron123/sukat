from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("scans", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "scans",
        sa.Column(
            "deleted_by",
            sa.Uuid(),
            sa.ForeignKey("users.id", name="fk_scans_deleted_by_users", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_scans_store_id_deleted_at",
        "scans",
        ["store_id", "deleted_at"],
        postgresql_where=sa.text("deleted_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_scans_store_id_deleted_at", table_name="scans")
    op.drop_column("scans", "deleted_by")
    op.drop_column("scans", "deleted_at")
