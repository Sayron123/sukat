"""store-safe stock movement -> line key.

stock_movements.transaction_item_id now references transaction_items by
(id, store_id), like every other child table, so a movement can never point at
another store's line. transaction_items gets UNIQUE (id, store_id) as the target.

Revision ID: 0005a
Revises: 0004
Create Date: 2026-11-05 09:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005a"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_stock_movements_transaction_item_id_transaction_items"
UQ = "uq_transaction_items_id_store_id"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(UQ, "transaction_items", ["id", "store_id"])
    op.drop_constraint(FK, "stock_movements", type_="foreignkey")
    op.create_foreign_key(
        FK,
        "stock_movements",
        "transaction_items",
        ["transaction_item_id", "store_id"],
        ["id", "store_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(FK, "stock_movements", type_="foreignkey")
    op.create_foreign_key(
        FK,
        "stock_movements",
        "transaction_items",
        ["transaction_item_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(UQ, "transaction_items", type_="unique")
