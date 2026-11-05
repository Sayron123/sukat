"""merge: transaction void (0005) and store-safe movement key (0005a).

Both came right after 0004 on separate branches (Phase 4 and the audit fixes).
They change different things, so they can run in either order. This empty
migration joins them into one head. A database at 0004, 0005 or 0005a all
upgrade cleanly with `alembic upgrade head`.

Revision ID: 0006
Revises: 0005, 0005a
Create Date: 2026-11-05 12:00:00.000000

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: str | Sequence[str] | None = ("0005", "0005a")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Nothing to change: this only joins the two branches."""


def downgrade() -> None:
    """Nothing to change: this only splits the two branches again."""
