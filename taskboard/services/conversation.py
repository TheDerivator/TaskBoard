"""Conversation use cases: timeline (posts + events), post/edit/delete posts, image uploads.

Posting needs `task.comment` on the task's section; reading needs `task.view`. Authors edit and
delete their own posts; user administrators may delete any post. Images are uploaded first (as
drafts), then linked to the post whose Markdown refers to them; drafts nobody posted are removed
after a day.
"""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from taskboard.db.base import utcnow
from taskboard.db.models import Attachment, Event, Post, Task, User
from taskboard.domain.access import Permission
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from taskboard.identity.principal import Principal
from taskboard.schemas.conversation import (
    Actor,
    AttachmentOut,
    Conversation,
    EventOut,
    PostCreate,
    PostOut,
    PostUpdate,
    TimelineItem,
)
from taskboard.services.attachments import (
    MAX_ATTACHMENT_BYTES,
    AttachmentStore,
    new_public_id,
    safe_filename,
    sniff_image_type,
)
from taskboard.services.markdown import ATTACHMENT_URL_PREFIX, attachment_ids_in, render_markdown
from taskboard.services.tasks import TaskService
from taskboard.services.visibility import ensure_usable

DRAFT_LIFETIME = timedelta(days=1)


def attachment_url(public_id: str, filename: str) -> str:
    """Percent-encoded, so names with spaces still form a valid Markdown link."""
    return f"{ATTACHMENT_URL_PREFIX}{public_id}/{quote(filename)}"


@dataclass(frozen=True)
class AttachmentFile:
    path: Path
    content_type: str
    filename: str


class ConversationService:
    def __init__(self, session: Session, principal: Principal, store: AttachmentStore) -> None:
        self.session = session
        self.principal = principal
        self.store = store
        self._tasks = TaskService(session, principal, store)

    # ------------------------------------------------------------------ reading

    def timeline(self, key: str, *, updates_only: bool = False) -> Conversation:
        task = self._tasks.find(key)
        posts = self.session.scalars(
            select(Post).where(Post.task_id == task.id).order_by(Post.created_at, Post.id)
        ).all()
        items: list[TimelineItem] = [
            self._post_out(p) for p in posts if p.is_update or not updates_only
        ]
        if not updates_only:
            events = self.session.scalars(
                select(Event).where(Event.task_id == task.id).order_by(Event.created_at, Event.id)
            ).all()
            items += [self._event_out(e) for e in events]
            items.sort(key=lambda item: (item.created_at, item.type == "post", item.id))
        return Conversation(
            items=items,
            post_count=len(posts),
            can_comment=self.principal.can(Permission.TASK_COMMENT, task.section_id),
        )

    @staticmethod
    def _actor(user: User) -> Actor:
        return Actor(user_id=user.id, display_name=user.display_name, person_id=user.person_id)

    def _post_out(self, post: Post) -> PostOut:
        return PostOut(
            id=post.id,
            author=self._actor(post.author),
            created_at=post.created_at,
            edited_at=post.edited_at,
            is_update=post.is_update,
            body_md=post.body_md,
            html=render_markdown(post.body_md),
            can_edit=post.author_user_id == self.principal.user_id
            and not self.principal.is_anonymous,
        )

    def _event_out(self, event: Event) -> EventOut:
        return EventOut(
            id=event.id,
            kind=event.kind,
            data=event.data,
            actor=self._actor(event.actor) if event.actor else None,
            created_at=event.created_at,
        )

    # ------------------------------------------------------------------ posting

    def add_post(self, key: str, data: PostCreate) -> PostOut:
        task = self._tasks.find(key)
        self.principal.require(Permission.TASK_COMMENT, task.section_id)
        body = data.body_md.strip()
        if not body:
            raise RuleViolationError("a post needs some text or an image")
        post = Post(
            task_id=task.id,
            author_user_id=self.principal.user_id,
            body_md=body,
            is_update=data.is_update,
        )
        self.session.add(post)
        self.session.flush()
        self._claim_attachments(post, task)
        self.session.commit()
        return self._post_out(post)

    def _own_post(self, post_id: int, *, for_delete: bool = False) -> tuple[Post, Task]:
        ensure_usable(self.principal)
        post = self.session.get(Post, post_id)
        if post is None:
            raise NotFoundError(f"no post {post_id}")
        task = self._tasks.find(self._key_of(post.task_id))  # the task must be visible
        is_author = (
            post.author_user_id == self.principal.user_id and not self.principal.is_anonymous
        )
        moderator = for_delete and self.principal.can(Permission.USERS_MANAGE)
        if not (is_author or moderator):
            raise PermissionDeniedError("only the author can change this post")
        return post, task

    def _key_of(self, task_id: int) -> str:
        key = self.session.scalar(select(Task.key).where(Task.id == task_id))
        if key is None:
            raise NotFoundError("the task is gone")
        return key

    def update_post(self, post_id: int, data: PostUpdate) -> PostOut:
        post, task = self._own_post(post_id)
        self.principal.require(Permission.TASK_COMMENT, task.section_id)
        body = data.body_md.strip()
        if not body:
            raise RuleViolationError("a post needs some text or an image")
        post.body_md = body
        post.is_update = data.is_update
        post.edited_at = utcnow()
        self._claim_attachments(post, task)
        self.session.commit()
        return self._post_out(post)

    def delete_post(self, post_id: int) -> None:
        post, _task = self._own_post(post_id, for_delete=True)
        files = list(
            self.session.scalars(select(Attachment.public_id).where(Attachment.post_id == post.id))
        )
        self.session.execute(delete(Attachment).where(Attachment.post_id == post.id))
        self.session.delete(post)
        self.session.commit()
        for public_id in files:
            self.store.delete(public_id)

    def _claim_attachments(self, post: Post, task: Task) -> None:
        """Link the uploader's draft images that this post's Markdown refers to."""
        referenced = attachment_ids_in(post.body_md)
        if not referenced:
            return
        drafts = self.session.scalars(
            select(Attachment).where(
                Attachment.public_id.in_(referenced),
                Attachment.task_id == task.id,
                Attachment.post_id.is_(None),
                Attachment.uploader_user_id == self.principal.user_id,
            )
        )
        for attachment in drafts:
            attachment.post_id = post.id

    # ------------------------------------------------------------------ files

    def upload(self, key: str, filename: str | None, data: bytes) -> AttachmentOut:
        task = self._tasks.find(key)
        self.principal.require(Permission.TASK_COMMENT, task.section_id)
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise RuleViolationError(
                f"images can be at most {MAX_ATTACHMENT_BYTES // 1_000_000} MB"
            )
        content_type = sniff_image_type(data)
        if content_type is None:
            raise RuleViolationError("only PNG, JPEG, GIF or WebP images can be attached")
        stale = self._remove_stale_drafts()
        attachment = Attachment(
            public_id=new_public_id(),
            task_id=task.id,
            uploader_user_id=self.principal.user_id,
            filename=safe_filename(filename, content_type),
            content_type=content_type,
            size=len(data),
        )
        self.store.save(attachment.public_id, data)
        self.session.add(attachment)
        self.session.commit()
        for public_id in stale:  # only once the database no longer refers to them
            self.store.delete(public_id)
        url = attachment_url(attachment.public_id, attachment.filename)
        return AttachmentOut(
            id=attachment.public_id,
            filename=attachment.filename,
            content_type=content_type,
            size=attachment.size,
            url=url,
            markdown=f"![{attachment.filename}]({url})",
        )

    def open_attachment(self, public_id: str) -> AttachmentFile:
        """The file behind an attachment, if the caller can see its task."""
        attachment = self.session.scalars(
            select(Attachment).where(Attachment.public_id == public_id)
        ).one_or_none()
        if attachment is None:
            raise NotFoundError("no such attachment")
        self._tasks.find(self._key_of(attachment.task_id))  # raises unless the task is visible
        path = self.store.path(attachment.public_id)
        if not path.exists():
            raise NotFoundError("the file is missing")
        return AttachmentFile(
            path=path, content_type=attachment.content_type, filename=attachment.filename
        )

    def _remove_stale_drafts(self) -> list[str]:
        """Delete draft rows nobody posted within a day; returns their ids (files go later)."""
        cutoff = utcnow() - DRAFT_LIFETIME
        stale = list(
            self.session.scalars(
                select(Attachment.public_id).where(
                    Attachment.post_id.is_(None), Attachment.created_at < cutoff
                )
            )
        )
        if stale:
            self.session.execute(delete(Attachment).where(Attachment.public_id.in_(stale)))
        return stale

    def preview(self, body: str) -> str:
        """Render Markdown exactly as a post would be (for the composer's Preview tab)."""
        ensure_usable(self.principal)
        if not self.principal.can_somewhere(Permission.TASK_COMMENT):
            if self.principal.is_anonymous:
                raise AuthenticationRequiredError("log in to write posts")
            raise PermissionDeniedError("you cannot write posts")
        return render_markdown(body)
