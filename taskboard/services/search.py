"""Search everything (DESIGN "Global search", M19): tasks (title, description, conversation),
process changes (key, title, what, why, periods, conversation), knowledge boxes (name,
description, key facts, key, step number, where they sit) and defects; every word of the query
must match somewhere, ignoring case across Unicode. Each type is filtered by its own view right,
exactly as its views are (nothing invisible is ever returned).

Long texts are matched in the database (one query per word, returning ids); short ones (names,
paths, tags) in Python. Only the best hits per type get their context worked out.
"""

from collections.abc import Iterable, Sequence
from contextlib import suppress
from datetime import date
from typing import Any

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Box,
    BoxKind,
    Change,
    ChangePeriod,
    Department,
    Person,
    Post,
    Process,
    Section,
    Task,
)
from taskboard.db.text import contains_ci
from taskboard.domain.access import Permission
from taskboard.domain.errors import AuthenticationRequiredError
from taskboard.domain.search import (
    holds,
    holds_all,
    plain,
    searchable,
    snippet,
    title_score,
    words_of,
)
from taskboard.domain.task_keys import InvalidTaskKeyError, display_key, normalize_key
from taskboard.identity.principal import Principal
from taskboard.schemas.search import SearchGroup, SearchHit, SearchResults
from taskboard.services.changes import ChangeService
from taskboard.services.tasks import permalink
from taskboard.services.visibility import ensure_usable, visible_changes, visible_tasks


def _facts_text(facts: list[list[Any]] | None) -> str:
    return " ".join(str(part) for fact in facts or [] for part in fact)


def _intersect(sets: Iterable[set[int]]) -> set[int]:
    result: set[int] | None = None
    for found in sets:
        result = found if result is None else result & found
        if not result:
            return set()
    return result or set()


class SearchService:
    def __init__(
        self, session: Session, principal: Principal, *, today: date | None = None
    ) -> None:
        self.session = session
        self.principal = principal
        self.today = today

    def _ids(self, query: Select[int]) -> set[int]:
        return set(self.session.scalars(query))

    def search(self, query: str, limit: int = 20) -> SearchResults:
        ensure_usable(self.principal)
        may = {
            p: not self.principal.reach(p).nowhere
            for p in (Permission.KNOWLEDGE_VIEW, Permission.CHANGE_VIEW, Permission.TASK_VIEW)
        }
        if not any(may.values()) and self.principal.is_anonymous:
            raise AuthenticationRequiredError("log in to search")
        words = words_of(query) if searchable(query) else []
        groups: dict[str, SearchGroup] = {}
        if may[Permission.KNOWLEDGE_VIEW]:
            groups["knowledge"], groups["defects"] = self._boxes(words, limit)
        if may[Permission.CHANGE_VIEW]:
            groups["changes"] = self._changes(words, limit)
        if may[Permission.TASK_VIEW]:
            groups["tasks"] = self._tasks(words, limit)
        order = ("knowledge", "changes", "tasks", "defects")
        return SearchResults(query=query, groups=[groups[t] for t in order if t in groups])

    # ------------------------------------------------------------------ tasks

    def _tasks(self, words: Sequence[str], limit: int) -> SearchGroup:
        if not words:
            return SearchGroup(type="tasks", total=0, hits=[])

        def matching(word: str) -> set[int]:
            posts = select(Post.task_id).where(
                Post.task_id.is_not(None), contains_ci(Post.body_md, word)
            )
            conditions = [
                contains_ci(Task.title, word),
                contains_ci(Task.description, word),
                Task.id.in_(posts),
            ]
            with suppress(InvalidTaskKeyError):  # "T-104" finds task 104
                conditions.append(Task.key == normalize_key(word))
            return self._ids(visible_tasks(select(Task.id), self.principal).where(or_(*conditions)))

        ids = _intersect(matching(w) for w in words)
        rows = list(
            self.session.execute(
                select(Task.id, Task.key, Task.title, Task.rank).where(in_ids(Task.id, ids))
            ).all()
        )
        rows.sort(key=lambda r: (-title_score(r.title, words), r.rank))
        best = {
            t.id: t
            for t in self.session.scalars(
                select(Task).where(in_ids(Task.id, [r.id for r in rows[:limit]]))
            )
        }
        hits = [self._task_hit(best[r.id], words) for r in rows[:limit]]
        return SearchGroup(type="tasks", total=len(rows), hits=hits)

    def _task_hit(self, task: Task, words: Sequence[str]) -> SearchHit:
        context = None
        if not holds_all([task.title], words):
            context = snippet(plain(task.description), words)
            if context is None:
                for body in self.session.scalars(
                    select(Post.body_md).where(Post.task_id == task.id).order_by(Post.id)
                ):
                    found = snippet(plain(body), words)
                    if found:
                        context = f"In conversation: “{found}”"
                        break
        if context is None:
            lead = self.session.get(Person, task.lead_person_id)
            context = " · ".join(filter(None, [task.status.label, lead and f"Lead {lead.name}"]))
        return SearchHit(
            type="tasks",
            key=task.key,
            ref=display_key(task.key),
            title=task.title,
            context=context,
            url=permalink(task.key),
        )

    # ------------------------------------------------------------------ process changes

    def _changes(self, words: Sequence[str], limit: int) -> SearchGroup:
        if not words:
            return SearchGroup(type="changes", total=0, hits=[])
        tags: dict[int, list[str]] = {}
        for change_id, scope_tags in self.session.execute(
            visible_changes(
                select(ChangePeriod.change_id, ChangePeriod.scope_tags).join(
                    Change, Change.id == ChangePeriod.change_id
                ),
                self.principal,
            )
        ).all():
            tags.setdefault(change_id, []).extend(str(t) for t in scope_tags)

        def matching(word: str) -> set[int]:
            posts = select(Post.change_id).where(
                Post.change_id.is_not(None), contains_ci(Post.body_md, word)
            )
            periods = select(ChangePeriod.change_id).where(contains_ci(ChangePeriod.label, word))
            conditions = or_(
                contains_ci(Change.key, word),
                contains_ci(Change.title, word),
                contains_ci(Change.what_md, word),
                contains_ci(Change.why_md, word),
                Change.id.in_(posts),
                Change.id.in_(periods),
            )
            found = self._ids(visible_changes(select(Change.id), self.principal).where(conditions))
            return found | {i for i, t in tags.items() if any(holds(tag, word) for tag in t)}

        ids = _intersect(matching(w) for w in words)
        rows = list(
            self.session.execute(
                select(Change.id, Change.key, Change.title).where(in_ids(Change.id, ids))
            ).all()
        )
        rows.sort(key=lambda r: (-title_score(f"{r.key} {r.title}", words), r.key))
        best = {
            c.id: c
            for c in self.session.scalars(
                select(Change).where(in_ids(Change.id, [r.id for r in rows[:limit]]))
            )
        }
        changes = [best[r.id] for r in rows[:limit]]
        summaries = ChangeService(self.session, self.principal, today=self.today).summaries(changes)
        processes = {p.id: p.name for p in self.session.scalars(select(Process))}
        hits: list[SearchHit] = []
        for change, summary in zip(changes, summaries, strict=True):
            hits.append(
                SearchHit(
                    type="changes",
                    key=change.key,
                    ref=change.key,
                    title=change.title,
                    context=self._change_context(change, summary.periods, tags, words) or "",
                    url=summary.url,
                    process=processes.get(change.process_id),
                    state=summary.state.state.value,
                    state_date=summary.state.date,
                )
            )
        return SearchGroup(type="changes", total=len(rows), hits=hits)

    def _change_context(
        self,
        change: Change,
        periods: Sequence[Any],
        tags: dict[int, list[str]],
        words: Sequence[str],
    ) -> str | None:
        """Nothing when the title says it all (the state shows); else where the match is."""
        if holds_all([change.key, change.title], words):
            return None
        for text in (change.what_md, change.why_md):
            found = snippet(plain(text), words)
            if found:
                return found
        for period in periods:
            line = " · ".join([period.label, *period.scope_tags])
            if any(holds(line, w) for w in words):
                return f"Period: {line}"
        for body in self.session.scalars(
            select(Post.body_md).where(Post.change_id == change.id).order_by(Post.id)
        ):
            found = snippet(plain(body), words)
            if found:
                return f"In conversation: “{found}”"
        return None

    # ------------------------------------------------------------------ knowledge and defects

    def _boxes(self, words: Sequence[str], limit: int) -> tuple[SearchGroup, SearchGroup]:
        if not words:
            return SearchGroup(type="knowledge", total=0, hits=[]), SearchGroup(
                type="defects", total=0, hits=[]
            )
        processes = {p.id: p for p in self.session.scalars(select(Process))}
        departments = dict(
            self.session.execute(
                select(Section.id, Department.code).join(
                    Department, Department.id == Section.department_id
                )
            ).all()
        )
        kinds = {k.id: k for k in self.session.scalars(select(BoxKind))}
        rows = self.session.execute(
            select(
                Box.id,
                Box.key,
                Box.name,
                Box.step_no,
                Box.facts,
                Box.main_url,
                Box.parent_id,
                Box.process_id,
                Box.section_id,
                Box.kind_id,
                Box.position,
            )
        ).all()
        by_id = {r.id: r for r in rows}

        def section(row: Any) -> int | None:
            if row.process_id is not None:
                process = processes.get(row.process_id)
                return process.section_id if process else None
            return row.section_id

        visible = [
            r
            for r in rows
            if (s := section(r)) is not None and self.principal.can(Permission.KNOWLEDGE_VIEW, s)
        ]

        def path(row: Any) -> list[str]:
            names: list[str] = []
            at = row.parent_id
            while at is not None and at in by_id and len(names) < 50:
                names.insert(0, by_id[at].name)
                at = by_id[at].parent_id
            return names

        paths = {r.id: path(r) for r in visible}
        in_bodies = [self._ids(select(Box.id).where(contains_ci(Box.body_md, w))) for w in words]

        def matches(row: Any) -> bool:
            facts = _facts_text(row.facts)
            short = [row.name, row.key, row.step_no, facts, row.main_url, " › ".join(paths[row.id])]
            folded = " \n".join(t.casefold() for t in short if t)
            return all(
                w in folded or row.id in body for w, body in zip(words, in_bodies, strict=True)
            )

        found = [r for r in visible if matches(r)]
        found.sort(key=lambda r: (-title_score(r.name, words), len(paths[r.id]), r.name.casefold()))
        groups: list[SearchGroup] = []
        for type_, defects in (("knowledge", False), ("defects", True)):
            of_type = [r for r in found if (r.process_id is None) == defects]
            best = of_type[:limit]
            bodies = dict(
                self.session.execute(
                    select(Box.id, Box.body_md).where(in_ids(Box.id, [r.id for r in best]))
                ).all()
            )
            hits = [
                self._box_hit(
                    r, bodies.get(r.id, ""), paths[r.id], kinds, processes, departments, words
                )
                for r in best
            ]
            groups.append(SearchGroup(type=type_, total=len(of_type), hits=hits))  # type: ignore[arg-type]
        return groups[0], groups[1]

    def _box_hit(
        self,
        row: Any,
        body: str,
        path: list[str],
        kinds: dict[int, BoxKind],
        processes: dict[int, Process],
        departments: dict[int, str],
        words: Sequence[str],
    ) -> SearchHit:
        kind = kinds.get(row.kind_id)
        is_defect = row.process_id is None
        found = snippet(plain(body), words) if not holds_all([row.name], words) else None
        if is_defect:
            department = departments.get(row.section_id, "")
            url = f"/cpl/{department}/{row.key}"
            context = found or (kind.name if kind else "Defect")
        else:
            process = processes[row.process_id]
            department = departments.get(process.section_id, "")
            url = f"/knowledge/{department}/{process.code}/{row.key}"
            name = "Process" if row.parent_id is None else (kind.name if kind else "Box")
            where = found or (row.main_url and row.main_url.split("://")[-1]) or " › ".join(path)
            context = f"{name} · {where}" if where else name
        return SearchHit(
            type="defects" if is_defect else "knowledge",
            key=row.key,
            ref="",
            title=row.name,
            context=context,
            url=url,
            style="root"
            if row.parent_id is None and not is_defect
            else (kind.style if kind else None),
        )
