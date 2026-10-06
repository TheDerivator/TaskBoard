"""Conversation use cases for tasks and process changes: timeline, posts, periods, history, images.

A conversation (a `Thread`) belongs to a task or to a process change, whose section decides the
rights: reading needs the view right, posting `task.comment` / `change.comment`. Authors edit and
delete their own posts; user administrators may delete any post. A change's periods are posts
too (DESIGN Module 2, rule 3), but structured change data: whoever may edit the change (A14)
edits or deletes them. Every edit keeps the earlier version (rule 6: "edited", history kept).
Images are uploaded first (as drafts), then linked to the post whose Markdown refers to them;
drafts nobody posted are removed after a day.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import ColumnElement, delete, func, select
from sqlalchemy.orm import Session

from taskboard.db.base import utcnow
from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Attachment,
    Change,
    ChangePeriod,
    Event,
    Post,
    PostRevision,
    Task,
    User,
)
from taskboard.domain.access import Permission
from taskboard.domain.changes import (
    PeriodKind,
    check_period,
    normalize_tags,
    period_label,
)
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    PermissionDeniedError,
    RuleViolationError,
)
from taskboard.identity.principal import Principal
from taskboard.schemas.changes import PeriodIn, PeriodUpdate
from taskboard.schemas.conversation import (
    Actor,
    AttachmentOut,
    Conversation,
    EventOut,
    PeriodOut,
    PostCreate,
    PostOut,
    PostUpdate,
    PostVersion,
    TimelineItem,
)
from taskboard.services.actors import actor
from taskboard.services.attachments import AttachmentStore, attachment_out, store_image
from taskboard.services.changes import ChangeService, period_out
from taskboard.services.knowledge import KnowledgeService
from taskboard.services.markdown import attachment_ids_in, render_markdown
from taskboard.services.tasks import TaskService
from taskboard.services.visibility import ensure_usable

DRAFT_LIFETIME = timedelta(days=1)


@dataclass(frozen=True)
class AttachmentFile:
    path: Path
    content_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class Thread:
    """One conversation: a task's or a process change's, and the section whose rights apply."""

    task_id: int | None
    change_id: int | None
    section_id: int

    @property
    def is_change(self) -> bool:
        return self.change_id is not None

    @property
    def comment(self) -> Permission:
        return Permission.CHANGE_COMMENT if self.is_change else Permission.TASK_COMMENT

    def of_post(self) -> ColumnElement[bool]:
        return Post.change_id == self.change_id if self.is_change else Post.task_id == self.task_id

    def of_attachment(self) -> ColumnElement[bool]:
        if self.is_change:
            return Attachment.change_id == self.change_id
        return Attachment.task_id == self.task_id


class ConversationService:
    def __init__(
        self,
        session: Session,
        principal: Principal,
        store: AttachmentStore,
        *,
        today: date | None = None,
    ) -> None:
        self.session = session
        self.principal = principal
        self.store = store
        self._tasks = TaskService(session, principal, store)
        self._changes = ChangeService(session, principal, today=today, store=store)

    # ------------------------------------------------------------------ threads

    def task_thread(self, key: str) -> Thread:
        """A visible task's conversation (otherwise not found)."""
        task = self._tasks.find(key)
        return Thread(task_id=task.id, change_id=None, section_id=task.section_id)

    def change_thread(self, key: str) -> Thread:
        """A visible process change's conversation (otherwise not found)."""
        change = self._changes.find(key)
        return Thread(task_id=None, change_id=change.id, section_id=change.process.section_id)

    def _thread_of(self, task_id: int | None, change_id: int | None) -> Thread:
        """The conversation a post or attachment belongs to, if the principal can see it."""
        if task_id is not None:
            key = self.session.scalar(select(Task.key).where(Task.id == task_id))
            if key is None:
                raise NotFoundError("the task is gone")
            return self.task_thread(key)
        key = self.session.scalar(select(Change.key).where(Change.id == change_id))
        if key is None:
            raise NotFoundError("the process change is gone")
        return self.change_thread(key)

    # ------------------------------------------------------------------ reading

    def timeline(
        self, thread: Thread, *, updates_only: bool = False, periods_only: bool = False
    ) -> Conversation:
        """Posts (and a task's events) oldest first; `updates_only` keeps a task's status
        updates, `periods_only` a change's period posts (events are left out with either)."""
        posts = self.session.scalars(
            select(Post).where(thread.of_post()).order_by(Post.created_at, Post.id)
        ).all()
        periods = self._periods_of(posts)
        versions = self._version_counts(posts)
        shown = [
            p
            for p in posts
            if (not updates_only or p.is_update) and (not periods_only or p.id in periods)
        ]
        items: list[TimelineItem] = [
            self._post_out(p, thread, periods.get(p.id), versions.get(p.id, 0) + 1) for p in shown
        ]
        if thread.task_id is not None and not (updates_only or periods_only):
            events = self.session.scalars(
                select(Event).where(Event.task_id == thread.task_id).order_by(Event.created_at)
            ).all()
            items += [self._event_out(e) for e in events]
            items.sort(key=lambda item: (item.created_at, item.type == "post", item.id))
        return Conversation(
            items=items,
            post_count=len(posts),
            can_comment=self.principal.can(thread.comment, thread.section_id),
            can_post_periods=thread.is_change
            and self.principal.can(Permission.CHANGE_EDIT, thread.section_id),
        )

    def _periods_of(self, posts: Sequence[Post]) -> dict[int, ChangePeriod]:
        ids = [p.id for p in posts if p.change_id is not None]
        if not ids:
            return {}
        rows = self.session.scalars(select(ChangePeriod).where(in_ids(ChangePeriod.post_id, ids)))
        return {period.post_id: period for period in rows}

    def _version_counts(self, posts: Sequence[Post]) -> dict[int, int]:
        """How many earlier versions each post has."""
        ids = [p.id for p in posts]
        if not ids:
            return {}
        rows = self.session.execute(
            select(PostRevision.post_id, func.count())
            .where(in_ids(PostRevision.post_id, ids))
            .group_by(PostRevision.post_id)
        ).all()
        return dict(rows)

    def _actor(self, user: User, token_id: int | None) -> Actor:
        return actor(self.session, user, token_id)

    def _is_author(self, post: Post) -> bool:
        return post.author_user_id == self.principal.user_id and not self.principal.is_anonymous

    def _post_out(
        self, post: Post, thread: Thread, period: ChangePeriod | None, versions: int
    ) -> PostOut:
        if period is not None:
            can_edit = self.principal.can(Permission.CHANGE_EDIT, thread.section_id)
        else:
            can_edit = self._is_author(post)
        return PostOut(
            id=post.id,
            author=self._actor(post.author, post.api_token_id),
            created_at=post.created_at,
            edited_at=post.edited_at,
            edited_by=self._actor(post.edited_by, post.edited_api_token_id)
            if post.edited_by
            else None,
            versions=versions,
            is_update=post.is_update,
            body_md=post.body_md,
            html=render_markdown(post.body_md),
            period=period_out(period) if period else None,
            can_edit=can_edit,
        )

    def _event_out(self, event: Event) -> EventOut:
        return EventOut(
            id=event.id,
            kind=event.kind,
            data=event.data,
            actor=self._actor(event.actor, event.api_token_id) if event.actor else None,
            created_at=event.created_at,
        )

    def history(self, post_id: int) -> list[PostVersion]:
        """Every version of a post, oldest first; the last one is the post as it is now."""
        post, _thread = self._post(post_id)  # the conversation must be visible
        period = self._periods_of([post]).get(post.id)
        revisions = self.session.scalars(
            select(PostRevision).where(PostRevision.post_id == post.id).order_by(PostRevision.rev)
        ).all()
        versions = [
            self._version(
                r.rev, self._actor(r.written_by, r.api_token_id), r.written_at, r.content, period
            )
            for r in revisions
        ]
        current = self._content(post, period)
        written_at = post.edited_at or post.created_at
        versions.append(
            self._version(len(revisions) + 1, self._last_writer(post), written_at, current, period)
        )
        return versions

    def _version(
        self,
        rev: int,
        written_by: Actor,
        written_at: datetime,
        content: dict[str, Any],
        period: ChangePeriod | None,
    ) -> PostVersion:
        fields = content.get("period")
        was = None
        if period is not None and fields is not None:
            end = fields["end_date"]
            was = PeriodOut(
                id=period.id,
                post_id=period.post_id,
                kind=PeriodKind(fields["kind"]),
                start_date=date.fromisoformat(fields["start_date"]),
                end_date=date.fromisoformat(end) if end else None,
                label=fields["label"],
                scope_tags=list(fields["scope_tags"]),
            )
        return PostVersion(
            rev=rev,
            written_by=written_by,
            written_at=written_at,
            is_update=bool(content.get("is_update", False)),
            body_md=content["body_md"],
            html=render_markdown(content["body_md"]),
            period=was,
        )

    @staticmethod
    def _content(post: Post, period: ChangePeriod | None) -> dict[str, Any]:
        """A post's content as stored in its history (JSON)."""
        content: dict[str, Any] = {"body_md": post.body_md, "is_update": post.is_update}
        if period is not None:
            content["period"] = {
                "kind": period.kind.value,
                "start_date": period.start_date.isoformat(),
                "end_date": period.end_date.isoformat() if period.end_date else None,
                "label": period.label,
                "scope_tags": list(period.scope_tags),
            }
        return content

    def _keep_version(self, post: Post, period: ChangePeriod | None) -> None:
        """Store the post as it is now, before it is edited."""
        count = self.session.scalar(select(func.count()).where(PostRevision.post_id == post.id))
        self.session.add(
            PostRevision(
                post_id=post.id,
                rev=(count or 0) + 1,
                content=self._content(post, period),
                written_by_user_id=post.edited_by_user_id or post.author_user_id,
                api_token_id=post.edited_api_token_id
                if post.edited_by_user_id
                else post.api_token_id,
                written_at=post.edited_at or post.created_at,
            )
        )

    def _last_writer(self, post: Post) -> Actor:
        if post.edited_by is not None:
            return self._actor(post.edited_by, post.edited_api_token_id)
        return self._actor(post.author, post.api_token_id)

    def _mark_edited(self, post: Post) -> None:
        post.edited_at = utcnow()
        post.edited_by_user_id = self.principal.user_id
        post.edited_api_token_id = self.principal.token_id

    # ------------------------------------------------------------------ posting

    def add_post(self, thread: Thread, data: PostCreate) -> PostOut:
        """A comment (for tasks optionally marked as a status update)."""
        self.principal.require(thread.comment, thread.section_id)
        body = data.body_md.strip()
        if not body:
            raise RuleViolationError("a post needs some text or an image")
        post = Post(
            task_id=thread.task_id,
            change_id=thread.change_id,
            author_user_id=self.principal.user_id,
            api_token_id=self.principal.token_id,
            body_md=body,
            is_update=data.is_update and not thread.is_change,
        )
        self.session.add(post)
        self.session.flush()
        self._claim_attachments(post, thread)
        self.session.commit()
        return self._post_out(post, thread, None, 1)

    def add_period(self, thread: Thread, data: PeriodIn) -> PostOut:
        """Post a test or a permanent process change in a change's conversation."""
        if not thread.is_change:
            raise RuleViolationError("periods belong to process changes")
        self.principal.require(Permission.CHANGE_EDIT, thread.section_id)
        check_period(data.kind, data.start_date, data.end_date)
        post = Post(
            change_id=thread.change_id,
            author_user_id=self.principal.user_id,
            api_token_id=self.principal.token_id,
            body_md=data.body_md.strip(),
        )
        self.session.add(post)
        self.session.flush()
        period = ChangePeriod(
            post_id=post.id,
            change_id=thread.change_id,
            kind=data.kind,
            start_date=data.start_date,
            end_date=data.end_date,
            label=period_label(data.kind, data.label),
            scope_tags=normalize_tags(data.scope_tags),
        )
        self.session.add(period)
        self._claim_attachments(post, thread)
        self.session.commit()
        return self._post_out(post, thread, period, 1)

    def _post(self, post_id: int) -> tuple[Post, Thread]:
        """A post in a conversation the principal can see."""
        ensure_usable(self.principal)
        post = self.session.get(Post, post_id)
        if post is None:
            raise NotFoundError(f"no post {post_id}")
        return post, self._thread_of(post.task_id, post.change_id)

    def update_post(self, post_id: int, data: PostUpdate) -> PostOut:
        """Edit a comment (its author, who must still be allowed to comment)."""
        post, thread = self._post(post_id)
        period = self._periods_of([post]).get(post.id)
        if period is not None:
            raise RuleViolationError("edit the period instead (PATCH /api/periods/{id})")
        if not self._is_author(post):
            raise PermissionDeniedError("only the author can change this post")
        self.principal.require(thread.comment, thread.section_id)
        body = data.body_md.strip()
        if not body:
            raise RuleViolationError("a post needs some text or an image")
        self._keep_version(post, None)
        post.body_md = body
        post.is_update = data.is_update and not thread.is_change
        self._mark_edited(post)
        self._claim_attachments(post, thread)
        self.session.commit()
        return self._post_out(post, thread, None, self._version_counts([post])[post.id] + 1)

    def update_period(self, period_id: int, data: PeriodUpdate) -> PostOut:
        """Edit a period (also "Set end date"): whoever may edit the change."""
        period = self.session.get(ChangePeriod, period_id)
        if period is None:
            raise NotFoundError(f"no period {period_id}")
        post, thread = self._post(period.post_id)
        self.principal.require(Permission.CHANGE_EDIT, thread.section_id)
        sent = data.model_fields_set
        kind = data.kind if data.kind is not None else period.kind
        start = data.start_date if data.start_date is not None else period.start_date
        end = data.end_date if "end_date" in sent else period.end_date
        check_period(kind, start, end)
        self._keep_version(post, period)
        period.kind, period.start_date, period.end_date = kind, start, end
        if "label" in sent:
            period.label = period_label(kind, data.label)
        if data.scope_tags is not None:
            period.scope_tags = normalize_tags(data.scope_tags)
        if data.body_md is not None:
            post.body_md = data.body_md.strip()
        self._mark_edited(post)
        self._claim_attachments(post, thread)
        self.session.commit()
        return self._post_out(post, thread, period, self._version_counts([post])[post.id] + 1)

    def delete_post(self, post_id: int) -> None:
        """Comments: their author, or a user administrator. Periods: whoever may edit the change."""
        post, thread = self._post(post_id)
        period = self._periods_of([post]).get(post.id)
        moderator = self.principal.can(Permission.USERS_MANAGE)
        if period is not None:
            allowed = self.principal.can(Permission.CHANGE_EDIT, thread.section_id)
        else:
            allowed = self._is_author(post)
        if not (allowed or moderator):
            raise PermissionDeniedError("you cannot delete this post")
        files = list(
            self.session.scalars(select(Attachment.public_id).where(Attachment.post_id == post.id))
        )
        if period is not None:
            self.session.delete(period)
        self.session.execute(delete(PostRevision).where(PostRevision.post_id == post.id))
        self.session.execute(delete(Attachment).where(Attachment.post_id == post.id))
        self.session.flush()
        self.session.delete(post)
        self.session.commit()
        for public_id in files:
            self.store.delete(public_id)

    def _claim_attachments(self, post: Post, thread: Thread) -> None:
        """Link the uploader's draft images that this post's Markdown refers to."""
        referenced = attachment_ids_in(post.body_md)
        if not referenced:
            return
        drafts = self.session.scalars(
            select(Attachment).where(
                Attachment.public_id.in_(referenced),
                thread.of_attachment(),
                Attachment.post_id.is_(None),
                Attachment.uploader_user_id == self.principal.user_id,
            )
        )
        for attachment in drafts:
            attachment.post_id = post.id

    # ------------------------------------------------------------------ files

    def upload(self, thread: Thread, filename: str | None, data: bytes) -> AttachmentOut:
        self.principal.require(thread.comment, thread.section_id)
        attachment = store_image(
            self.store,
            filename,
            data,
            task_id=thread.task_id,
            change_id=thread.change_id,
            uploader_user_id=self.principal.user_id,
        )
        stale = self._remove_stale_drafts()
        self.session.add(attachment)
        self.session.commit()
        for public_id in stale:  # only once the database no longer refers to them
            self.store.delete(public_id)
        return attachment_out(attachment)

    def open_attachment(self, public_id: str) -> AttachmentFile:
        """The file behind an attachment, if the caller can see its task, change or box."""
        attachment = self.session.scalars(
            select(Attachment).where(Attachment.public_id == public_id)
        ).one_or_none()
        if attachment is None:
            raise NotFoundError("no such attachment")
        if attachment.box_id is not None:
            KnowledgeService(self.session, self.principal).box_by_id(attachment.box_id)
        else:
            self._thread_of(attachment.task_id, attachment.change_id)  # raises unless visible
        path = self.store.path(attachment.public_id)
        if not path.exists():
            raise NotFoundError("the file is missing")
        return AttachmentFile(
            path=path, content_type=attachment.content_type, filename=attachment.filename
        )

    def _remove_stale_drafts(self) -> list[str]:
        """Delete draft rows nobody posted within a day; returns their ids (files go later).
        A box's images are never drafts: its description (and its history) uses them."""
        cutoff = utcnow() - DRAFT_LIFETIME
        stale = list(
            self.session.scalars(
                select(Attachment.public_id).where(
                    Attachment.post_id.is_(None),
                    Attachment.box_id.is_(None),
                    Attachment.created_at < cutoff,
                )
            )
        )
        if stale:
            self.session.execute(delete(Attachment).where(Attachment.public_id.in_(stale)))
        return stale

    def preview(self, body: str) -> str:
        """Markdown rendered as a post would be (Preview of posts and box descriptions)."""
        ensure_usable(self.principal)
        writers = (
            Permission.TASK_COMMENT,
            Permission.CHANGE_COMMENT,
            Permission.CHANGE_EDIT,
            Permission.KNOWLEDGE_EDIT,  # box descriptions
        )
        if not any(self.principal.can_somewhere(p) for p in writers):
            if self.principal.is_anonymous:
                raise AuthenticationRequiredError("log in to write posts")
            raise PermissionDeniedError("you cannot write posts")
        return render_markdown(body)
