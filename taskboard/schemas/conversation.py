"""Conversation shapes (tasks and process changes): timeline of posts, periods and events, post
commands, earlier versions of posts, attachments, preview."""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.changes import PeriodKind
from taskboard.domain.events import EventKind

Body = Annotated[str, StringConstraints(max_length=20_000)]


class Actor(BaseModel):
    user_id: int | None
    display_name: str
    person_id: int | None  # for the avatar; None for accounts that are not people


class PeriodOut(BaseModel):
    """A process change's test or permanent change, posted in its conversation."""

    id: int
    post_id: int
    kind: PeriodKind
    start_date: date
    end_date: date | None  # inclusive; None for a process change still in effect
    label: str
    scope_tags: list[str]


class PostOut(BaseModel):
    type: Literal["post"] = "post"
    id: int
    author: Actor
    created_at: datetime
    edited_at: datetime | None
    edited_by: Actor | None = None  # who edited last (periods may be edited by others)
    versions: int = 1  # more than 1: earlier versions are kept (GET /api/posts/{id}/history)
    is_update: bool
    body_md: str
    html: str  # sanitized; safe to insert as-is
    period: PeriodOut | None = None  # set for the period posts of a process change
    can_edit: bool  # edit and delete


class EventOut(BaseModel):
    type: Literal["event"] = "event"
    id: int
    kind: EventKind
    data: dict[str, Any]
    actor: Actor | None
    created_at: datetime


TimelineItem = Annotated[PostOut | EventOut, Field(discriminator="type")]


class Conversation(BaseModel):
    items: list[TimelineItem]  # oldest first
    post_count: int
    can_comment: bool
    can_post_periods: bool = False  # process changes: `change.edit`


class PostVersion(BaseModel):
    """One version of a post, as it was written; the last one is the current post."""

    rev: int
    written_by: Actor
    written_at: datetime
    is_update: bool
    body_md: str
    html: str
    period: PeriodOut | None  # the period as it was, for period posts


class PostCreate(BaseModel):
    body_md: Body
    is_update: bool = False


class PostUpdate(BaseModel):
    body_md: Body
    is_update: bool


class AttachmentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size: int
    url: str  # relative to the app's base path, e.g. "api/attachments/<id>/map.png"
    markdown: str  # ready to insert: ![map.png](api/attachments/<id>/map.png)


class MarkdownPreviewIn(BaseModel):
    body_md: Body


class MarkdownPreviewOut(BaseModel):
    html: str
