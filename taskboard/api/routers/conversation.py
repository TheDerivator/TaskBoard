"""Conversation endpoints: a task's timeline and posts, editing and history of any post, image
uploads and downloads, Markdown preview. (A process change's conversation: routers/changes.py.)"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from taskboard.api.deps import Conversations
from taskboard.schemas.conversation import (
    AttachmentOut,
    Conversation,
    MarkdownPreviewIn,
    MarkdownPreviewOut,
    PostCreate,
    PostOut,
    PostUpdate,
    PostVersion,
)
from taskboard.services.attachments import MAX_ATTACHMENT_BYTES

router = APIRouter(tags=["conversation"])


@router.get("/tasks/{key}/conversation")
def conversation(
    key: str, conversations: Conversations, updates_only: bool = False
) -> Conversation:
    """Posts and automatic events, oldest first. `updates_only` keeps only status updates."""
    return conversations.timeline(conversations.task_thread(key), updates_only=updates_only)


@router.post("/tasks/{key}/posts", status_code=status.HTTP_201_CREATED)
def add_post(key: str, body: PostCreate, conversations: Conversations) -> PostOut:
    """Markdown body; images referenced from uploads of yours are attached to the post."""
    return conversations.add_post(conversations.task_thread(key), body)


@router.patch("/posts/{post_id}")
def update_post(post_id: int, body: PostUpdate, conversations: Conversations) -> PostOut:
    return conversations.update_post(post_id, body)


@router.delete("/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, conversations: Conversations) -> None:
    """Also a change's period post (by whoever may edit the change)."""
    conversations.delete_post(post_id)


@router.get("/posts/{post_id}/history")
def post_history(post_id: int, conversations: Conversations) -> list[PostVersion]:
    """Every version of an edited post, oldest first; the last is the post as it is now."""
    return conversations.history(post_id)


@router.post("/tasks/{key}/attachments", status_code=status.HTTP_201_CREATED)
def upload_attachment(
    key: str, file: Annotated[UploadFile, File()], conversations: Conversations
) -> AttachmentOut:
    """Upload an image (PNG, JPEG, GIF, WebP; at most 10 MB) to use in a post."""
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    return conversations.upload(conversations.task_thread(key), file.filename, data)


@router.get("/attachments/{public_id}/{filename}", response_class=FileResponse)
def download_attachment(
    public_id: str, filename: str, conversations: Conversations
) -> FileResponse:
    """The image, for anyone who can see its task or change. `filename` is only cosmetic."""
    del filename
    found = conversations.open_attachment(public_id)
    return FileResponse(
        found.path,
        media_type=found.content_type,
        filename=found.filename,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=86400", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/markdown/preview")
def preview(body: MarkdownPreviewIn, conversations: Conversations) -> MarkdownPreviewOut:
    """Render Markdown exactly as a post would be shown."""
    return MarkdownPreviewOut(html=conversations.preview(body.body_md))
