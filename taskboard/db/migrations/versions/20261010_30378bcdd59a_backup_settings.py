"""backup settings (how many backups to keep, set under Administration › Backups)

Revision ID: 30378bcdd59a
Revises: 743649b1221b
Create Date: 2026-10-10 13:31:16.831048
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import taskboard.db.base

revision: str = "30378bcdd59a"
down_revision: str | None = "743649b1221b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backup_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("keep_newest", sa.Integer(), nullable=False),
        sa.Column("keep_weekly", sa.Integer(), nullable=False),
        sa.Column("keep_monthly", sa.Integer(), nullable=False),
        sa.Column("updated_at", taskboard.db.base.UTCDateTime(), nullable=False),
        sa.Column("updated_by_user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            name=op.f("fk_backup_settings_updated_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_backup_settings")),
    )


def downgrade() -> None:
    op.drop_table("backup_settings")
