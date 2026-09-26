"""Task conversation: Markdown posts, uploaded attachments, and automatic events."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, ForeignKey, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, ShortText, Text, UTCDateTime, str_enum, utcnow
from taskboard.db.models.identity import User
from taskboard.domain.events import EventKind


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    edited_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    body_md: Mapped[str] = mapped_column(Text)
    is_update: Mapped[bool] = mapped_column(default=False)  # highlighted "status update"

    author: Mapped[User] = relationship()


class Attachment(Base):
    """An uploaded file (images for now). Stored under <data_dir>/uploads/<public_id>."""

    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(Unicode(32), unique=True)  # random hex, used in URLs
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
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
