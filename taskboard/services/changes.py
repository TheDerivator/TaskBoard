"""Process-change use cases: list a process's changes, read, create, edit, move, delete; scope tags.

Rights follow the process's owning section (D-080): `change.view` to read, `change.edit` to create
and edit (moving a change to another process needs it on both), `change.delete` to delete.
Periods and comments are posts in the change's conversation (services/conversation.py). States
are derived from the periods on the server's date (domain/changes.py), never stored.
"""

from collections import Counter
from collections.abc import Iterable
from datetime import date
from urllib.parse import quote

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Attachment,
    Box,
    Change,
    ChangePeriod,
    Department,
    Person,
    Post,
    PostRevision,
    Process,
    Reference,
    Section,
)
from taskboard.db.session import CHANGE_NUMBER_LOCK, acquire_lock
from taskboard.domain.access import Permission
from taskboard.domain.changes import Period, change_key, change_state, normalize_change_key
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    NotFoundError,
    RuleViolationError,
    StaleVersionError,
)
from taskboard.identity.principal import Principal
from taskboard.schemas.changes import (
    ChangeCreate,
    ChangeDetail,
    ChangePermissions,
    ChangeSummary,
    ChangeUpdate,
    StateOut,
)
from taskboard.schemas.conversation import PeriodOut
from taskboard.services.attachments import AttachmentStore
from taskboard.services.markdown import render_markdown
from taskboard.services.visibility import ensure_usable, visible_changes


def period_out(period: ChangePeriod) -> PeriodOut:
    return PeriodOut(
        id=period.id,
        post_id=period.post_id,
        kind=period.kind,
        start_date=period.start_date,
        end_date=period.end_date,
        label=period.label,
        scope_tags=[str(t) for t in period.scope_tags],
    )


def _sorted_periods(periods: Iterable[ChangePeriod]) -> list[ChangePeriod]:
    return sorted(periods, key=lambda p: (p.start_date, p.id))


class ChangeService:
    def __init__(
        self,
        session: Session,
        principal: Principal,
        *,
        today: date | None = None,  # the server's date: states depend on it
        store: AttachmentStore | None = None,  # to remove the images of deleted changes
    ) -> None:
        self.session = session
        self.principal = principal
        self.today = today or date.today()
        self.store = store

    # ------------------------------------------------------------------ processes

    def process(self, code: str, permission: Permission = Permission.CHANGE_VIEW) -> Process:
        """A process by its code, if the principal holds `permission` in its owning section."""
        ensure_usable(self.principal)
        process = self.session.scalars(
            select(Process).where(Process.code == code.strip().upper())
        ).one_or_none()
        if process is None or not self.principal.can(Permission.CHANGE_VIEW, process.section_id):
            if self.principal.is_anonymous and self.principal.reach(Permission.CHANGE_VIEW).nowhere:
                raise AuthenticationRequiredError("log in to see process changes")
            raise NotFoundError(f"no process {code}")
        self.principal.require(permission, process.section_id)
        return process

    def _process_by_id(self, process_id: int, permission: Permission) -> Process:
        process = self.session.get(Process, process_id)
        if process is None:
            raise NotFoundError(f"no process {process_id}")
        return self.process(process.code, permission)

    def _paths(self) -> dict[int, str]:
        """Each process's part of a change URL: "STL/LM"."""
        rows = self.session.execute(
            select(Process.id, Process.code, Department.code)
            .join(Section, Section.id == Process.section_id)
            .join(Department, Department.id == Section.department_id)
        )
        return {pid: f"{quote(dept, safe='')}/{quote(code, safe='')}" for pid, code, dept in rows}

    # ------------------------------------------------------------------ reading

    def find(self, key: str) -> Change:
        """A change the principal can see; invisible ones are reported as not found."""
        query = visible_changes(
            select(Change).where(Change.key == normalize_change_key(key)), self.principal
        )
        change = self.session.scalars(query).one_or_none()
        if change is None:
            raise NotFoundError(f"no process change {key}")
        return change

    def list(self, process_code: str) -> list[ChangeSummary]:
        """A process's changes, newest first (by number)."""
        process = self.process(process_code)
        changes = list(
            self.session.scalars(
                select(Change)
                .where(Change.process_id == process.id)
                .order_by(Change.number.desc(), Change.id.desc())
            )
        )
        return self.summaries(changes)

    def get(self, key: str) -> ChangeDetail:
        return self._detail(self.find(key))

    def summaries(self, changes: list[Change]) -> list[ChangeSummary]:
        ids = [c.id for c in changes]
        periods: dict[int, list[ChangePeriod]] = {}
        if ids:
            for period in self.session.scalars(
                select(ChangePeriod).where(in_ids(ChangePeriod.change_id, ids))
            ):
                periods.setdefault(period.change_id, []).append(period)
        counts = dict(
            self.session.execute(
                select(Post.change_id, func.count())
                .where(in_ids(Post.change_id, ids))
                .group_by(Post.change_id)
            ).all()
        )
        paths = self._paths()
        boxes = self._box_keys(ids)
        return [
            self._summary(c, periods.get(c.id, []), counts.get(c.id, 0), paths).model_copy(
                update={"box_keys": boxes.get(c.id, [])}
            )
            for c in changes
        ]

    def _box_keys(self, change_ids: list[int]) -> dict[int, list[str]]:
        """The knowledge-map boxes each change is linked to, where the reader may see them."""
        reach = self.principal.reach(Permission.KNOWLEDGE_VIEW)
        if not change_ids or reach.nowhere:
            return {}
        sections = {p.id: p.section_id for p in self.session.scalars(select(Process))}
        rows = self.session.execute(
            select(Reference.change_id, Box.key, Box.process_id, Box.section_id)
            .join(Box, Box.id == Reference.box_id)
            .where(in_ids(Reference.change_id, change_ids))
            .order_by(Box.key)
        ).all()
        result: dict[int, list[str]] = {}
        for change_id, key, process_id, section_id in rows:
            section = sections[process_id] if process_id is not None else section_id
            if change_id is not None and section is not None and reach.includes(section):
                result.setdefault(change_id, []).append(key)
        return result

    def _summary(
        self,
        change: Change,
        periods: list[ChangePeriod],
        post_count: int,
        paths: dict[int, str],
    ) -> ChangeSummary:
        ordered = _sorted_periods(periods)
        state = change_state(
            (Period(p.kind, p.start_date, p.end_date) for p in ordered), self.today
        )
        return ChangeSummary(
            key=change.key,
            url=f"/changes/{paths[change.process_id]}/{change.key}",
            process_id=change.process_id,
            title=change.title,
            what_md=change.what_md,
            why_md=change.why_md,
            owner_person_id=change.owner_person_id,
            periods=[period_out(p) for p in ordered],
            state=StateOut(state=state.state, date=state.date),
            post_count=post_count,
            updated_at=change.updated_at,
            version=change.version,
        )

    def _detail(self, change: Change) -> ChangeDetail:
        summary = self.summaries([change])[0]
        section_id = change.process.section_id
        return ChangeDetail(
            **summary.model_dump(),
            created_at=change.created_at,
            what_html=render_markdown(change.what_md),
            why_html=render_markdown(change.why_md),
            permissions=ChangePermissions(
                edit=self.principal.can(Permission.CHANGE_EDIT, section_id),
                comment=self.principal.can(Permission.CHANGE_COMMENT, section_id),
                delete=self.principal.can(Permission.CHANGE_DELETE, section_id),
            ),
        )

    def scope_tags(self, process_code: str) -> list[str]:
        """Tags already used on the process's periods, most used first (DESIGN rule 4)."""
        process = self.process(process_code)
        counts: Counter[str] = Counter()
        spelling: dict[str, str] = {}
        tags = self.session.scalars(
            select(ChangePeriod.scope_tags)
            .join(Change, Change.id == ChangePeriod.change_id)
            .where(Change.process_id == process.id)
        )
        for row in tags:
            for tag in row:
                text = str(tag)
                counts[text.casefold()] += 1
                spelling.setdefault(text.casefold(), text)
        ranked = sorted(counts, key=lambda k: (-counts[k], spelling[k].casefold()))
        return [spelling[k] for k in ranked]

    # ------------------------------------------------------------------ editing

    def _owner(self, person_id: int) -> Person:
        person = self.session.get(Person, person_id)
        if person is None:
            raise NotFoundError(f"no person {person_id}")
        if not person.active:
            raise RuleViolationError(f"{person.name} is no longer active")
        return person

    def create(self, data: ChangeCreate) -> ChangeDetail:
        process = self._process_by_id(data.process_id, Permission.CHANGE_EDIT)
        owner = self._owner(data.owner_person_id)
        acquire_lock(self.session, CHANGE_NUMBER_LOCK)
        last = self.session.scalar(
            select(func.max(Change.number)).where(Change.key.like(f"{process.code}-%"))
        )
        number = (last or 0) + 1
        change = Change(
            key=change_key(process.code, number),
            number=number,
            process_id=process.id,
            title=data.title,
            what_md=data.what_md,
            why_md=data.why_md,
            owner_person_id=owner.id,
            created_by_user_id=None if self.principal.is_anonymous else self.principal.user_id,
        )
        self.session.add(change)
        self.session.commit()
        return self._detail(change)

    def update(self, key: str, data: ChangeUpdate) -> ChangeDetail:
        change = self.find(key)
        self.principal.require(Permission.CHANGE_EDIT, change.process.section_id)
        if data.version != change.version:
            raise StaleVersionError("someone else changed this process change; reload it")
        if data.process_id is not None and data.process_id != change.process_id:
            # Moving: edit rights on both processes. The key stays (stable links).
            change.process_id = self._process_by_id(data.process_id, Permission.CHANGE_EDIT).id
        if data.owner_person_id is not None and data.owner_person_id != change.owner_person_id:
            change.owner_person_id = self._owner(data.owner_person_id).id
        for field in ("title", "what_md", "why_md"):
            value = getattr(data, field)
            if value is not None:
                setattr(change, field, value)
        self.session.commit()
        self.session.refresh(change)
        return self._detail(change)

    def delete(self, key: str) -> None:
        """For good, with its conversation (periods, posts, their versions and images)."""
        change = self.find(key)
        self.principal.require(Permission.CHANGE_DELETE, change.process.section_id)
        posts = select(Post.id).where(Post.change_id == change.id)
        files = list(
            self.session.scalars(
                select(Attachment.public_id).where(Attachment.change_id == change.id)
            )
        )
        self.session.execute(delete(Reference).where(Reference.change_id == change.id))
        self.session.execute(delete(ChangePeriod).where(ChangePeriod.change_id == change.id))
        self.session.execute(delete(PostRevision).where(PostRevision.post_id.in_(posts)))
        self.session.execute(delete(Attachment).where(Attachment.change_id == change.id))
        self.session.execute(delete(Post).where(Post.change_id == change.id))
        self.session.delete(change)
        self.session.commit()
        if self.store is not None:
            for public_id in files:
                self.store.delete(public_id)
