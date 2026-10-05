"""Process-change endpoints: a process's changes, one change, its conversation and periods."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from taskboard.api.deps import Changes, Conversations
from taskboard.schemas.changes import (
    ChangeCreate,
    ChangeDetail,
    ChangeSummary,
    ChangeUpdate,
    PeriodIn,
    PeriodUpdate,
)
from taskboard.schemas.conversation import AttachmentOut, Conversation, PostCreate, PostOut
from taskboard.services.attachments import MAX_ATTACHMENT_BYTES

router = APIRouter(tags=["process changes"])


@router.get("/changes")
def list_changes(process: str, changes: Changes) -> list[ChangeSummary]:
    """A process's changes (by process code, e.g. `LM`), newest first, with their periods and
    the state they are in today."""
    return changes.list(process)


@router.post("/changes", status_code=status.HTTP_201_CREATED)
def create_change(body: ChangeCreate, changes: Changes) -> ChangeDetail:
    """The key is the process code and the next free number (`LM-13`)."""
    return changes.create(body)


@router.get("/changes/{key}")
def get_change(key: str, changes: Changes) -> ChangeDetail:
    """By key, ignoring case (`lm-07`)."""
    return changes.get(key)


@router.patch("/changes/{key}")
def update_change(key: str, body: ChangeUpdate, changes: Changes) -> ChangeDetail:
    """`version` must be the one last read (else 409). A new `process_id` moves the change."""
    return changes.update(key, body)


@router.delete("/changes/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_change(key: str, changes: Changes) -> None:
    """For good, with its conversation (`change.delete`, Administrators by default)."""
    changes.delete(key)


@router.get("/changes/{key}/conversation")
def change_conversation(
    key: str, conversations: Conversations, periods_only: bool = False
) -> Conversation:
    """Comments and period posts, oldest first. `periods_only` keeps the periods."""
    return conversations.timeline(conversations.change_thread(key), periods_only=periods_only)


@router.post("/changes/{key}/posts", status_code=status.HTTP_201_CREATED)
def add_comment(key: str, body: PostCreate, conversations: Conversations) -> PostOut:
    """A comment in Markdown; images referenced from uploads of yours are attached to it."""
    return conversations.add_post(conversations.change_thread(key), body)


@router.post("/changes/{key}/periods", status_code=status.HTTP_201_CREATED)
def add_period(key: str, body: PeriodIn, conversations: Conversations) -> PostOut:
    """Post a test (with an end date) or a permanent process change (without)."""
    return conversations.add_period(conversations.change_thread(key), body)


@router.patch("/periods/{period_id}")
def update_period(period_id: int, body: PeriodUpdate, conversations: Conversations) -> PostOut:
    """Edit a period; the earlier version is kept. "Set end date": `{"end_date": "…"}`."""
    return conversations.update_period(period_id, body)


@router.post("/changes/{key}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    key: str, file: Annotated[UploadFile, File()], conversations: Conversations
) -> AttachmentOut:
    """Upload an image (PNG, JPEG, GIF, WebP; at most 10 MB) to use in a post."""
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    return conversations.upload(conversations.change_thread(key), file.filename, data)


@router.get("/processes/{code}/scope-tags")
def scope_tags(code: str, changes: Changes) -> list[str]:
    """Scope tags already used on this process's periods, most used first (for suggestions)."""
    return changes.scope_tags(code)
