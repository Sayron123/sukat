"""foreign key delete rules: block deletes that would destroy or orphan history.

Changes these foreign keys to ON DELETE RESTRICT:
- every store_id -> stores
- transaction_items -> transactions
- stock_movements -> transaction_items
- transactions.created_by, transactions.voided_by, scans.created_by,
  stock_movements.created_by -> users
- store_members.user_id -> users

Left as they are: product_aliases and unit_conversions -> products (CASCADE) and
invites.invited_by_user_id -> users (SET NULL).

created_by becomes NOT NULL on each table that has no NULLs. A table that does have
NULLs keeps a nullable column, and a warning names it, because those rows need a real
creator before the rule can be added.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05 21:00:00.000000

"""

import logging
from collections.abc import Sequence
from typing import NamedTuple

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

log = logging.getLogger("alembic.runtime.migration")


class Fk(NamedTuple):
    """One foreign key, and the delete rule it had before this migration."""

    table: str
    columns: list[str]
    target: str
    target_columns: list[str]
    old_ondelete: str

    @property
    def name(self) -> str:
        # Same pattern as NAMING_CONVENTION in app/core/base.py.
        return f"fk_{self.table}_{self.columns[0]}_{self.target}"


FKS = [
    *(
        Fk(table, ["store_id"], "stores", ["id"], "CASCADE")
        for table in (
            "ai_usage",
            "invites",
            "product_aliases",
            "products",
            "scans",
            "stock_movements",
            "store_members",
            "transaction_items",
            "transactions",
            "unit_conversions",
        )
    ),
    Fk(
        "transaction_items",
        ["transaction_id", "store_id"],
        "transactions",
        ["id", "store_id"],
        "CASCADE",
    ),
    Fk(
        "stock_movements",
        ["transaction_item_id", "store_id"],
        "transaction_items",
        ["id", "store_id"],
        "CASCADE",
    ),
    Fk("transactions", ["created_by"], "users", ["id"], "SET NULL"),
    Fk("transactions", ["voided_by"], "users", ["id"], "SET NULL"),
    Fk("scans", ["created_by"], "users", ["id"], "SET NULL"),
    Fk("stock_movements", ["created_by"], "users", ["id"], "SET NULL"),
    Fk("store_members", ["user_id"], "users", ["id"], "CASCADE"),
]

CREATED_BY_TABLES = ("scans", "stock_movements", "transactions")


def _set_ondelete(fk: Fk, ondelete: str) -> None:
    op.drop_constraint(fk.name, fk.table, type_="foreignkey")
    op.create_foreign_key(
        fk.name, fk.table, fk.target, fk.columns, fk.target_columns, ondelete=ondelete
    )


def upgrade() -> None:
    """Upgrade schema."""
    for fk in FKS:
        _set_ondelete(fk, "RESTRICT")

    conn = op.get_bind()
    for table in CREATED_BY_TABLES:
        # Table names come from the constant above, never from input.
        has_nulls = conn.scalar(
            sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} WHERE created_by IS NULL)")
        )
        if has_nulls:
            log.warning("%s.created_by has NULLs: leaving the column nullable", table)
        else:
            op.alter_column(table, "created_by", existing_type=sa.Uuid(), nullable=False)


def downgrade() -> None:
    """Downgrade schema. Safe to run whether or not upgrade() could add NOT NULL."""
    for table in CREATED_BY_TABLES:
        op.alter_column(table, "created_by", existing_type=sa.Uuid(), nullable=True)

    for fk in FKS:
        _set_ondelete(fk, fk.old_ondelete)
