"""box images

Revision ID: a58ea5830fe1
Revises: accb969d56e3
Create Date: 2026-10-04 22:51:32.502817
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a58ea5830fe1"
down_revision: str | None = "accb969d56e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ONE_OWNER = (
    "(task_id IS NOT NULL AND change_id IS NULL) OR (task_id IS NULL AND change_id IS NOT NULL)"
)
ONE_IMAGE_OWNER = (
    "(task_id IS NOT NULL AND change_id IS NULL AND box_id IS NULL)"
    " OR (task_id IS NULL AND change_id IS NOT NULL AND box_id IS NULL)"
    " OR (task_id IS NULL AND change_id IS NULL AND box_id IS NOT NULL)"
)


def upgrade() -> None:
    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("box_id", sa.Integer(), nullable=True))
        batch_op.create_index(batch_op.f("ix_attachments_box_id"), ["box_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_attachments_box_id_boxes"), "boxes", ["box_id"], ["id"]
        )
        batch_op.drop_constraint(batch_op.f("ck_attachments_one_owner"), type_="check")
        batch_op.create_check_constraint(op.f("ck_attachments_one_owner"), ONE_IMAGE_OWNER)


def downgrade() -> None:
    op.execute("DELETE FROM attachments WHERE box_id IS NOT NULL")  # boxes had no images before
    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_attachments_one_owner"), type_="check")
        batch_op.create_check_constraint(op.f("ck_attachments_one_owner"), ONE_OWNER)
        batch_op.drop_constraint(batch_op.f("fk_attachments_box_id_boxes"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_attachments_box_id"))
        batch_op.drop_column("box_id")
