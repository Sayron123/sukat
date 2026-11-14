from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=True)
    op.add_column("users", sa.Column("username", sa.String(30), nullable=True))
    op.create_unique_constraint(op.f("uq_users_username"), "users", ["username"])
    op.create_check_constraint(
        op.f("ck_users_username_lowercase"), "users", "username = lower(username)"
    )
    op.create_check_constraint(
        op.f("ck_users_email_or_username"), "users", "email IS NOT NULL OR username IS NOT NULL"
    )
    op.alter_column("invites", "email", existing_type=sa.String(320), nullable=True)
    op.add_column("invites", sa.Column("name", sa.String(60), nullable=True))
    op.drop_constraint(op.f("ck_auth_tokens_purpose"), "auth_tokens", type_="check")
    op.create_check_constraint(
        op.f("ck_auth_tokens_purpose"),
        "auth_tokens",
        "purpose IN ('password_reset', 'email_verify', 'staff_reset')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM auth_tokens WHERE purpose = 'staff_reset'")
    op.drop_constraint(op.f("ck_auth_tokens_purpose"), "auth_tokens", type_="check")
    op.create_check_constraint(
        op.f("ck_auth_tokens_purpose"),
        "auth_tokens",
        "purpose IN ('password_reset', 'email_verify')",
    )
    op.drop_column("invites", "name")
    op.execute("DELETE FROM invites WHERE email IS NULL")
    op.alter_column("invites", "email", existing_type=sa.String(320), nullable=False)
    op.drop_constraint(op.f("ck_users_email_or_username"), "users", type_="check")
    op.drop_constraint(op.f("ck_users_username_lowercase"), "users", type_="check")
    op.drop_constraint(op.f("uq_users_username"), "users", type_="unique")
    op.drop_column("users", "username")
    op.alter_column("users", "email", existing_type=sa.String(320), nullable=False)
