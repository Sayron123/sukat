"""store address: add an optional address to stores.

Nullable because stores that already exist have no address yet.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-05 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add stores.address."""
    op.add_column("stores", sa.Column("address", sa.String(length=300), nullable=True))


def downgrade() -> None:
    """Remove stores.address. Any saved addresses are lost."""
    op.drop_column("stores", "address")
