from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_identities", sa.Column("email", sa.String(320), nullable=True))


def downgrade() -> None:
    op.drop_column("user_identities", "email")
