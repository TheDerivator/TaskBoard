"""process changes

Revision ID: 5337a4d5fc47
Revises: 43353ae16098
Create Date: 2026-10-04 15:40:48.976061

Process changes and their periods. Posts and attachments now belong to a task *or* a change, and
posts keep their earlier versions. Order matters on MS SQL: the posts' new (id, change_id) key
must exist before change_periods refers to it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import taskboard.db.base

revision: str = "5337a4d5fc47"
down_revision: str | None = "43353ae16098"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ONE_OWNER = (
    "(task_id IS NOT NULL AND change_id IS NULL) OR (task_id IS NULL AND change_id IS NOT NULL)"
)


def upgrade() -> None:
    op.create_table(
        "changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.Unicode(length=20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("process_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.Unicode(length=300), nullable=False),
        sa.Column("what_md", sa.UnicodeText().with_variant(sa.NVARCHAR(), "mssql"), nullable=False),
        sa.Column("why_md", sa.UnicodeText().with_variant(sa.NVARCHAR(), "mssql"), nullable=False),
        sa.Column("owner_person_id", sa.Integer(), nullable=False),
        sa.Column("created_at", taskboard.db.base.UTCDateTime(), nullable=False),
        sa.Column("updated_at", taskboard.db.base.UTCDateTime(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], name=op.f("fk_changes_created_by_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["owner_person_id"], ["people.id"], name=op.f("fk_changes_owner_person_id_people")
        ),
        sa.ForeignKeyConstraint(
            ["process_id"], ["processes.id"], name=op.f("fk_changes_process_id_processes")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_changes")),
        sa.UniqueConstraint("key", name=op.f("uq_changes_key")),
    )
    with op.batch_alter_table("changes", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_changes_owner_person_id"), ["owner_person_id"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_changes_process_id"), ["process_id"], unique=False)

    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.add_column(sa.Column("change_id", sa.Integer(), nullable=True))
        batch_op.alter_column("task_id", existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_index(batch_op.f("ix_attachments_change_id"), ["change_id"], unique=False)
        batch_op.create_foreign_key(
            batch_op.f("fk_attachments_change_id_changes"), "changes", ["change_id"], ["id"]
        )
        batch_op.create_check_constraint(op.f("ck_attachments_one_owner"), ONE_OWNER)

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("change_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("edited_by_user_id", sa.Integer(), nullable=True))
        batch_op.alter_column("task_id", existing_type=sa.INTEGER(), nullable=True)
        batch_op.create_index(batch_op.f("ix_posts_change_id"), ["change_id"], unique=False)
        batch_op.create_unique_constraint(batch_op.f("uq_posts_id_change_id"), ["id", "change_id"])
        batch_op.create_foreign_key(
            batch_op.f("fk_posts_edited_by_user_id_users"), "users", ["edited_by_user_id"], ["id"]
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_posts_change_id_changes"), "changes", ["change_id"], ["id"]
        )
        batch_op.create_check_constraint(op.f("ck_posts_one_owner"), ONE_OWNER)

    op.create_table(
        "change_periods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("change_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("test", "change", name="periodkind", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("label", sa.Unicode(length=100), nullable=False),
        sa.Column("scope_tags", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["change_id"], ["changes.id"], name=op.f("fk_change_periods_change_id_changes")
        ),
        sa.ForeignKeyConstraint(
            ["post_id", "change_id"],
            ["posts.id", "posts.change_id"],
            name="fk_change_periods_post_same_change",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_periods")),
        sa.UniqueConstraint("post_id", name=op.f("uq_change_periods_post_id")),
    )
    with op.batch_alter_table("change_periods", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_change_periods_change_id"), ["change_id"], unique=False
        )

    op.create_table(
        "post_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("post_id", sa.Integer(), nullable=False),
        sa.Column("rev", sa.Integer(), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("written_by_user_id", sa.Integer(), nullable=False),
        sa.Column("written_at", taskboard.db.base.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_post_revisions_post_id_posts")
        ),
        sa.ForeignKeyConstraint(
            ["written_by_user_id"],
            ["users.id"],
            name=op.f("fk_post_revisions_written_by_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post_revisions")),
        sa.UniqueConstraint("post_id", "rev", name=op.f("uq_post_revisions_post_id_rev")),
    )
    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_post_revisions_post_id"), ["post_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_post_revisions_post_id"))
    op.drop_table("post_revisions")

    with op.batch_alter_table("change_periods", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_change_periods_change_id"))
    op.drop_table("change_periods")

    # Change conversations cannot exist without changes; task_id becomes required again.
    op.execute("DELETE FROM attachments WHERE change_id IS NOT NULL")
    op.execute("DELETE FROM posts WHERE change_id IS NOT NULL")

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_posts_one_owner"), type_="check")
        batch_op.drop_constraint(batch_op.f("fk_posts_change_id_changes"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_posts_edited_by_user_id_users"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("uq_posts_id_change_id"), type_="unique")
        batch_op.drop_index(batch_op.f("ix_posts_change_id"))
        batch_op.alter_column("task_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column("edited_by_user_id")
        batch_op.drop_column("change_id")

    with op.batch_alter_table("attachments", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("ck_attachments_one_owner"), type_="check")
        batch_op.drop_constraint(batch_op.f("fk_attachments_change_id_changes"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_attachments_change_id"))
        batch_op.alter_column("task_id", existing_type=sa.INTEGER(), nullable=False)
        batch_op.drop_column("change_id")

    with op.batch_alter_table("changes", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_changes_process_id"))
        batch_op.drop_index(batch_op.f("ix_changes_owner_person_id"))
    op.drop_table("changes")
