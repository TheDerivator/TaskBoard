"""api tokens (and which token wrote each event, post, revision and release)

Revision ID: 743649b1221b
Revises: d8d4a375aeac
Create Date: 2026-10-06 21:10:28.986336
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import taskboard.db.base

revision: str = "743649b1221b"
down_revision: str | None = "d8d4a375aeac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Unicode(length=100), nullable=False),
        sa.Column("token_hash", sa.Unicode(length=64), nullable=False),
        sa.Column("prefix", sa.Unicode(length=16), nullable=False),
        sa.Column(
            "scope",
            sa.Enum("read", "write", name="tokenscope", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("created_at", taskboard.db.base.UTCDateTime(), nullable=False),
        sa.Column("expires_at", taskboard.db.base.UTCDateTime(), nullable=True),
        sa.Column("last_used_at", taskboard.db.base.UTCDateTime(), nullable=True),
        sa.Column("last_used_ip", sa.Unicode(length=45), nullable=True),
        sa.Column("revoked_at", taskboard.db.base.UTCDateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_api_tokens_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_api_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_api_tokens_token_hash")),
    )
    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_api_tokens_user_id"), ["user_id"], unique=False)

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_token_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_events_api_token_id_api_tokens"), "api_tokens", ["api_token_id"], ["id"]
        )

    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_token_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_post_revisions_api_token_id_api_tokens"),
            "api_tokens",
            ["api_token_id"],
            ["id"],
        )

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_token_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("edited_api_token_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_posts_api_token_id_api_tokens"), "api_tokens", ["api_token_id"], ["id"]
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_posts_edited_api_token_id_api_tokens"),
            "api_tokens",
            ["edited_api_token_id"],
            ["id"],
        )

    with op.batch_alter_table("releases", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_token_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_releases_api_token_id_api_tokens"),
            "api_tokens",
            ["api_token_id"],
            ["id"],
        )

    with op.batch_alter_table("revisions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("api_token_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_revisions_api_token_id_api_tokens"),
            "api_tokens",
            ["api_token_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("revisions", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_revisions_api_token_id_api_tokens"), type_="foreignkey"
        )
        batch_op.drop_column("api_token_id")

    with op.batch_alter_table("releases", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_releases_api_token_id_api_tokens"), type_="foreignkey"
        )
        batch_op.drop_column("api_token_id")

    with op.batch_alter_table("posts", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_posts_edited_api_token_id_api_tokens"), type_="foreignkey"
        )
        batch_op.drop_constraint(batch_op.f("fk_posts_api_token_id_api_tokens"), type_="foreignkey")
        batch_op.drop_column("edited_api_token_id")
        batch_op.drop_column("api_token_id")

    with op.batch_alter_table("post_revisions", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_post_revisions_api_token_id_api_tokens"), type_="foreignkey"
        )
        batch_op.drop_column("api_token_id")

    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_events_api_token_id_api_tokens"), type_="foreignkey"
        )
        batch_op.drop_column("api_token_id")

    with op.batch_alter_table("api_tokens", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_api_tokens_user_id"))

    op.drop_table("api_tokens")
