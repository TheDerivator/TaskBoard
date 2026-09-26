"""Conversation shapes: timeline of posts and events, post commands, attachments, preview."""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.events import EventKind

Body = Annotated[str, StringConstraints(max_length=20_000)]


class Actor(BaseModel):
    user_id: int | None
    display_name: str
    person_id: int | None  # for the avatar; None for accounts that are not people


class PostOut(BaseModel):
    type: Literal["post"] = "post"
    id: int
    author: Actor
    created_at: datetime
    edited_at: datetime | None
    is_update: bool
    body_md: str
    html: str  # sanitized; safe to insert as-is
    can_edit: bool


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
