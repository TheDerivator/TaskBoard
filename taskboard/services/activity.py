"""Recent activity (M25, D-104): tasks and process changes by their newest post, newest first.

Only what the principal may see is listed, each type by its own view right, exactly like its
views. Comments, status updates and periods count; automatic events and edits do not. Pages end at
a cursor (the newest post of their last item), so new posts never repeat an item on a later page.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import ColumnElement, Select, and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from taskboard.db.ids import in_ids
from taskboard.db.models import Change, ChangePeriod, Post, Process, Task
from taskboard.domain.access import Permission
from taskboard.domain.activity import ActivityType, Cursor, excerpt, post_kind
from taskboard.domain.errors import AuthenticationRequiredError, RuleViolationError
from taskboard.identity.principal import Principal
from taskboard.schemas.activity import (
    ActivityItem,
    ActivityPage,
    ActivityQuery,
    ChangeActivity,
    LastPost,
    TaskActivity,
)
from taskboard.schemas.tasks import TaskFilter
from taskboard.services.actors import actor
from taskboard.services.catalog import Catalog
from taskboard.services.changes import ChangeService
from taskboard.services.tasks import filtered_tasks, summarize, with_card_data
from taskboard.services.visibility import ensure_usable, visible_changes, visible_tasks


@dataclass(frozen=True, slots=True)
class _Newest:
    """The newest post of a conversation, and how many posts it has."""

    post_id: int
    task_id: int | None
    change_id: int | None
    at: datetime
    posts: int


class ActivityService:
    def __init__(
        self, session: Session, principal: Principal, *, today: date | None = None
    ) -> None:
        self.session = session
        self.principal = principal
        self._changes = ChangeService(session, principal, today=today)  # their summaries

    def recent(self, query: ActivityQuery) -> ActivityPage:
        ensure_usable(self.principal)
        may_tasks = not self.principal.reach(Permission.TASK_VIEW).nowhere
        may_changes = not self.principal.reach(Permission.CHANGE_VIEW).nowhere
        if not (may_tasks or may_changes) and self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to see the board")
        try:
            cursor = Cursor.decode(query.before) if query.before else None
        except ValueError as error:
            raise RuleViolationError("`before` must be the `next` of an earlier page") from error

        types = set(query.types or ActivityType)
        catalog = Catalog.load(self.session)
        threads: list[ColumnElement[bool]] = []
        if ActivityType.TASK in types and may_tasks and query.process_id is None:
            threads.append(Post.task_id.in_(self._task_ids(query, catalog)))
        if (
            ActivityType.CHANGE in types
            and may_changes
            and query.project_id is None
            and query.node_id is None
        ):
            threads.append(Post.change_id.in_(self._change_ids(query, catalog)))
        if not threads:
            return ActivityPage(items=[], next=None)

        newest = self._newest_posts(threads, cursor, query.limit + 1)
        page = newest[: query.limit]
        end = Cursor(page[-1].at, page[-1].post_id) if len(newest) > query.limit else None
        return ActivityPage(items=self._items(page, catalog), next=end.encode() if end else None)

    def _newest_posts(
        self, threads: list[ColumnElement[bool]], cursor: Cursor | None, limit: int
    ) -> list[_Newest]:
        """The newest post of each of these conversations, newest first, older than the cursor."""
        thread = (Post.task_id, Post.change_id)
        ranked = (
            select(
                Post.id,
                Post.task_id,
                Post.change_id,
                Post.created_at,
                func.row_number()
                .over(partition_by=thread, order_by=(Post.created_at.desc(), Post.id.desc()))
                .label("newest"),
                func.count().over(partition_by=thread).label("posts"),
            )
            .where(or_(*threads))
            .subquery()
        )
        query = select(ranked).where(ranked.c.newest == 1)
        if cursor is not None:
            query = query.where(
                or_(
                    ranked.c.created_at < cursor.at,
                    and_(ranked.c.created_at == cursor.at, ranked.c.id < cursor.post_id),
                )
            )
        rows = self.session.execute(
            query.order_by(ranked.c.created_at.desc(), ranked.c.id.desc()).limit(limit)
        )
        return [_Newest(r.id, r.task_id, r.change_id, r.created_at, r.posts) for r in rows]

    def _items(self, newest: list[_Newest], catalog: Catalog) -> list[ActivityItem]:
        """Each conversation's task or process change, with its newest post."""
        posts = {
            p.id: p
            for p in self.session.scalars(
                select(Post)
                .options(selectinload(Post.author))
                .where(in_ids(Post.id, [n.post_id for n in newest]))
            )
        }
        periods = set(
            self.session.scalars(
                select(ChangePeriod.post_id).where(in_ids(ChangePeriod.post_id, list(posts)))
            )
        )
        tasks = {
            t.id: summarize(t, catalog)
            for t in self.session.scalars(
                with_card_data(
                    select(Task).where(
                        in_ids(Task.id, [n.task_id for n in newest if n.task_id is not None])
                    )
                )
            )
        }
        change_rows = list(
            self.session.scalars(
                select(Change).where(
                    in_ids(Change.id, [n.change_id for n in newest if n.change_id is not None])
                )
            )
        )
        changes = dict(
            zip([c.id for c in change_rows], self._changes.summaries(change_rows), strict=True)
        )

        items: list[ActivityItem] = []
        for n in newest:
            post = posts[n.post_id]
            last = LastPost(
                id=post.id,
                kind=post_kind(is_update=post.is_update, is_period=post.id in periods),
                author=actor(self.session, post.author, post.api_token_id),
                created_at=post.created_at,
                excerpt=excerpt(post.body_md),
            )
            if n.task_id is not None:
                items.append(
                    TaskActivity(task=tasks[n.task_id], last_post=last, post_count=n.posts)
                )
            elif n.change_id is not None:
                items.append(
                    ChangeActivity(change=changes[n.change_id], last_post=last, post_count=n.posts)
                )
        return items

    def _task_ids(self, query: ActivityQuery, catalog: Catalog) -> Select[int]:
        """The visible tasks that pass the filters (the same rules as the task list)."""
        filters = TaskFilter(
            department_id=query.department_id,
            section_id=query.section_id,
            project_id=query.project_id,
            node_id=query.node_id,
        )
        return filtered_tasks(visible_tasks(select(Task.id), self.principal), filters, catalog)

    def _change_ids(self, query: ActivityQuery, catalog: Catalog) -> Select[int]:
        """The visible process changes that pass the filters (by their process's owning section)."""
        changes = visible_changes(select(Change.id), self.principal)
        if query.process_id is not None:
            changes = changes.where(Change.process_id == query.process_id)
        if query.department_id is not None:
            sections = catalog.section_ids_of_department(query.department_id)
            in_department = select(Process.id).where(Process.section_id.in_(sections))
            changes = changes.where(Change.process_id.in_(in_department))
        if query.section_id is not None:
            in_section = select(Process.id).where(Process.section_id == query.section_id)
            changes = changes.where(Change.process_id.in_(in_section))
        return changes
