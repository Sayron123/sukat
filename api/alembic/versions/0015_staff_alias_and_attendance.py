from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("store_members", sa.Column("alias", sa.String(length=120), nullable=True))
    op.create_table(
        "attendance",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("member_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("note", sa.String(length=300), nullable=True),
        sa.Column("recorded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('present', 'late', 'half_day', 'absent')",
            name=op.f("ck_attendance_status"),
        ),
        sa.ForeignKeyConstraint(
            ["member_id"],
            ["store_members.id"],
            name=op.f("fk_attendance_member_id_store_members"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["users.id"],
            name=op.f("fk_attendance_recorded_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_attendance_store_id_stores"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attendance")),
        sa.UniqueConstraint(
            "member_id", "work_date", name=op.f("uq_attendance_member_id_work_date")
        ),
    )
    op.create_index(op.f("ix_attendance_store_id"), "attendance", ["store_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_attendance_store_id"), table_name="attendance")
    op.drop_table("attendance")
    op.drop_column("store_members", "alias")
