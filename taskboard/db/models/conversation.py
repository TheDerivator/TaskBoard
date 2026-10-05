"""Conversations of tasks and process changes: Markdown posts (with their earlier versions),
uploaded attachments, and automatic task events."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, ShortText, Text, UTCDateTime, str_enum, utcnow
from taskboard.db.models.identity import User
from taskboard.domain.events import EventKind

# A post or attachment belongs to exactly one conversation: a task's or a process change's.
# (Written without comparing booleans, which MS SQL cannot do.)
ONE_OWNER = (
    "(task_id IS NOT NULL AND change_id IS NULL) OR (task_id IS NULL AND change_id IS NOT NULL)"
)
# An image belongs to a task's or a change's conversation, or to a box's description.
ONE_IMAGE_OWNER = (
    "(task_id IS NOT NULL AND change_id IS NULL AND box_id IS NULL)"
    " OR (task_id IS NULL AND change_id IS NOT NULL AND box_id IS NULL)"
    " OR (task_id IS NULL AND change_id IS NULL AND box_id IS NOT NULL)"
)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(ONE_OWNER, name="one_owner"),
        UniqueConstraint("id", "change_id"),  # target of change_periods' "same change" key
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Who edited last; a period post may be edited by others than its author.
    edited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    body_md: Mapped[str] = mapped_column(Text)
    is_update: Mapped[bool] = mapped_column(default=False)  # highlighted "status update" (tasks)

    author: Mapped[User] = relationship(foreign_keys=[author_user_id])
    edited_by: Mapped[User | None] = relationship(foreign_keys=[edited_by_user_id])


class PostRevision(Base):
    """An earlier version of a post, kept when the post is edited ("edited", history kept)."""

    __tablename__ = "post_revisions"
    __table_args__ = (UniqueConstraint("post_id", "rev"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"), index=True)
    rev: Mapped[int]  # 1 = the post as first written
    # The content as it was (body, and a period's fields), who wrote it and when.
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    written_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    written_at: Mapped[datetime] = mapped_column(UTCDateTime)

    written_by: Mapped[User] = relationship()


class Attachment(Base):
    """An uploaded image. Stored under <data_dir>/uploads/<public_id>. A conversation's images
    start as drafts (no post yet); a box's images belong to its description."""

    __tablename__ = "attachments"
    __table_args__ = (CheckConstraint(ONE_IMAGE_OWNER, name="one_owner"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(Unicode(32), unique=True)  # random hex, used in URLs
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id"), index=True)
    box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"), index=True)
    post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"), index=True)
    uploader_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    filename: Mapped[str] = mapped_column(Unicode(255))
    content_type: Mapped[str] = mapped_column(ShortText)
    size: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Event(Base):
    """Something that happened to a task, recorded automatically (see domain/events.py)."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    kind: Mapped[EventKind] = mapped_column(str_enum(EventKind, length=40))
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    actor: Mapped[User | None] = relationship()
