from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scans", sa.Column("rescans", sa.SmallInteger(), server_default="0", nullable=False)
    )
    op.execute(
        """
        DELETE FROM scans
        WHERE status = 'read'
          AND jsonb_typeof(ai_result_json -> 'lines') = 'array'
          AND jsonb_array_length(ai_result_json -> 'lines') = 0
          AND NOT EXISTS (SELECT 1 FROM transactions t WHERE t.scan_id = scans.id)
        """
    )


def downgrade() -> None:
    op.drop_column("scans", "rescans")
