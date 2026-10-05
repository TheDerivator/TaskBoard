"""Releases of a process's FMEA and control plan (DESIGN Versioning 2-4): the released versions,
the draft since the latest one (computed, never stored) and releasing, which needs
`knowledge.release` on the process's section and has no approval step (D-081).

A release freezes the current revision of every box, link and control in its scope
(domain/releases.py); an old version is drawn from those revisions alone (services/frozen.py).
"""

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Box,
    BoxKind,
    BoxLink,
    Control,
    LinkType,
    Process,
    Release,
    ReleaseItem,
    Revision,
    User,
)
from taskboard.domain.access import Permission
from taskboard.domain.errors import ConflictError, RuleViolationError
from taskboard.domain.knowledge import ObjectType
from taskboard.domain.releases import (
    Document,
    DraftItem,
    ObjectKey,
    Verb,
    draft,
    label,
    next_number,
    release_scope,
    warnings,
)
from taskboard.identity.principal import Principal
from taskboard.schemas.conversation import Actor
from taskboard.schemas.knowledge import (
    Draft,
    DraftEntry,
    DraftLine,
    ReleaseIn,
    ReleaseList,
    ReleaseOut,
)
from taskboard.services.frozen import FrozenState, frozen_state, snapshot
from taskboard.services.knowledge import KnowledgeService

RELEASE = Permission.KNOWLEDGE_RELEASE
OBJECT_NAMES = {ObjectType.CONTROL: "Control", ObjectType.LINK: "Link"}


class _Current:
    """The process's knowledge objects as they are now, and what its documents would hold."""

    def __init__(self, session: Session, process: Process) -> None:
        own = list(session.scalars(select(Box).where(Box.process_id == process.id)))
        own_ids = [b.id for b in own]
        self.links = list(
            session.scalars(select(BoxLink).where(in_ids(BoxLink.from_box_id, own_ids)))
        )
        targets = {lk.to_box_id for lk in self.links} - set(own_ids)
        self.boxes = [*own, *session.scalars(select(Box).where(in_ids(Box.id, targets)))]
        self.controls = list(
            session.scalars(select(Control).where(in_ids(Control.box_id, own_ids)))
        )
        self.kinds = {k.id: k for k in session.scalars(select(BoxKind))}
        self.types = {t.id: t for t in session.scalars(select(LinkType))}
        self.snapshot = snapshot(self.boxes, self.links, self.controls, self.kinds, self.types)
        self.scope = release_scope(process.id, self.snapshot)
        self.revs: dict[ObjectKey, int] = {
            **{(ObjectType.BOX, b.id): b.rev for b in self.boxes},
            **{(ObjectType.LINK, lk.id): lk.rev for lk in self.links},
            **{(ObjectType.CONTROL, c.id): c.rev for c in self.controls},
        }
        self.own_ids = own_ids


class ReleaseService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        self.knowledge = KnowledgeService(session, principal)

    # ------------------------------------------------------------------ reading

    def _actor(self, user_id: int | None) -> Actor | None:
        user = self.session.get(User, user_id) if user_id is not None else None
        if user is None:
            return None
        return Actor(user_id=user.id, display_name=user.display_name, person_id=user.person_id)

    def _out(self, release: Release) -> ReleaseOut:
        items = self.session.scalar(
            select(func.count()).where(ReleaseItem.release_id == release.id)
        )
        return ReleaseOut(
            number=release.number,
            label=label(release.number),
            note=release.note,
            released_by=self._actor(release.released_by_user_id),
            released_at=release.released_at,
            items=items or 0,
        )

    def _releases(self, process: Process) -> list[Release]:
        return list(
            self.session.scalars(
                select(Release)
                .where(Release.process_id == process.id)
                .order_by(Release.number.desc())
            )
        )

    def releases(self, process_code: str) -> ReleaseList:
        """The process's released versions, newest first, and the draft since the latest."""
        process = self.knowledge.process(process_code)
        releases = self._releases(process)
        base = releases[0] if releases else None
        return ReleaseList(
            releases=[self._out(r) for r in releases],
            draft=self._draft(process, base, _Current(self.session, process)),
            can_release=self.principal.can(RELEASE, process.section_id),
        )

    def _items(
        self, base: Release | None, now: _Current, process: Process
    ) -> tuple[list[DraftItem], FrozenState | None]:
        current = {key: (now.revs[key], docs) for key, docs in now.scope.items()}
        if base is None:
            return draft(current, {}, now.revs), None
        state = frozen_state(self.session, base.id)
        frozen = snapshot(state.boxes, state.links, state.controls, now.kinds, now.types)
        frozen_scope = release_scope(process.id, frozen)
        released = {
            key: (revision.rev, frozen_scope.get(key, frozenset()))
            for key, revision in state.revisions.items()
        }
        revisions = dict(now.revs)
        for object_type, model in (
            (ObjectType.BOX, Box),
            (ObjectType.LINK, BoxLink),
            (ObjectType.CONTROL, Control),
        ):  # objects frozen in the release that are no longer here (moved elsewhere)
            missing = [i for (t, i) in released if t is object_type and (t, i) not in revisions]
            for object_id, rev in self.session.execute(
                select(model.id, model.rev).where(in_ids(model.id, missing))
            ).all():
                revisions[object_type, object_id] = rev
        added = self._revisions({key: now.revs[key] for key in current if key not in released})
        unchanged = [key for key, rev in added.items() if rev.created_at <= base.released_at]
        return draft(current, released, revisions, unchanged), state

    def _revisions(self, wanted: dict[ObjectKey, int | None]) -> dict[ObjectKey, Revision]:
        """For each object its revision `rev`, or with None its latest (a deletion); one query per
        kind of object rather than one per object."""
        found: dict[ObjectKey, Revision] = {}
        for object_type in ObjectType:
            ids = [i for (t, i) in wanted if t is object_type]
            if not ids:
                continue
            for revision in self.session.scalars(
                select(Revision)
                .where(Revision.object_type == object_type, in_ids(Revision.object_id, ids))
                .order_by(Revision.rev)
            ):
                key = (object_type, revision.object_id)
                rev = wanted[key]
                if rev is None or revision.rev == rev:
                    found[key] = revision  # ordered by rev: None ends at the latest
        return found

    def _draft(self, process: Process, base: Release | None, now: _Current) -> Draft:
        items, state = self._items(base, now, process)
        names: dict[int, str] = {b.id: b.name for b in (state.boxes if state else [])}
        names |= {b.id: b.name for b in now.boxes}
        boxes = {b.id: b for b in now.boxes}
        frozen_boxes = {b.id: b for b in state.boxes} if state else {}
        cautions = warnings(process.id, now.snapshot)
        since = f" since {label(base.number)}" if base else ""

        revisions = self._revisions({(i.object_type, i.object_id): i.after for i in items})
        grouped: dict[int, list[tuple[DraftItem, Revision | None]]] = {}
        for item in items:
            revision = revisions.get((item.object_type, item.object_id))
            box_id = revision.box_id if revision else item.object_id
            grouped.setdefault(box_id, []).append((item, revision))

        entries: list[tuple[datetime | None, DraftEntry]] = []
        markers: dict[str, str] = {}
        for box_id, changes in grouped.items():
            box = boxes.get(box_id) or frozen_boxes.get(box_id)
            if box is None:
                continue
            own = next((i for i, _ in changes if i.object_type is ObjectType.BOX), None)
            verb = own.verb if own else Verb.CHANGED
            lines = [self._line(item, revision, state, names, boxes) for item, revision in changes]
            documents = {d for item, _ in changes for d in item.documents}
            entry = DraftEntry(
                box_key=box.key,
                box_name=box.name,
                verb=verb,
                documents=[d for d in Document if d in documents],
                lines=lines,
                warnings=[str(w) for w in cautions.get(box_id, [])] if verb != Verb.REMOVED else [],
            )
            latest = max((line.at for line in lines if line.at), default=None)
            entries.append((latest, entry))
            if verb is not Verb.REMOVED:
                markers[box.key] = _marker(own, [i for i, _ in changes], since)
        entries.sort(key=lambda e: (e[0] is None, e[0] or datetime.min, e[1].box_name))
        outside = 0
        if base is not None:
            touched = self.session.execute(
                select(Revision.object_type, Revision.object_id)
                .where(in_ids(Revision.box_id, now.own_ids), Revision.created_at > base.released_at)
                .distinct()
            ).all()
            frozen_keys: set[ObjectKey] = set(state.revisions) if state else set()
            outside = len({(t, i) for t, i in touched} - set(now.scope) - frozen_keys)
        listed = [e for _, e in entries]
        return Draft(
            base=base.number if base else None,
            entries=listed,
            fmea=sum(Document.FMEA in e.documents for e in listed),
            cpl=sum(Document.CPL in e.documents for e in listed),
            outside_scope=outside,
            markers=markers,
        )

    def _line(
        self,
        item: DraftItem,
        revision: Revision | None,
        state: FrozenState | None,
        names: dict[int, str],
        boxes: dict[int, Box],
    ) -> DraftLine:
        key = (item.object_type, item.object_id)
        before: dict[str, Any] | None = None
        if state is not None and key in state.revisions:
            before = state.revisions[key].content
        if revision is None:
            summary = "Removed"
        elif item.object_type is ObjectType.BOX and item.verb is Verb.ADDED:
            summary = _new_box(revision.content, boxes)
        elif item.verb is Verb.REMOVED and not revision.deleted:
            summary = "No longer in the FMEA or control plan"
        else:
            summary = KnowledgeService.summary(revision, before, names)
        return DraftLine(
            object_type=item.object_type,
            verb=item.verb,
            summary=summary,
            author=self._actor(revision.author_user_id) if revision else None,
            at=revision.created_at if revision else None,
            before=item.before,
            after=item.after,
        )

    # ------------------------------------------------------------------ releasing

    def release(self, process_code: str, data: ReleaseIn) -> ReleaseOut:
        """Freeze the current scope as the next version, if the draft reviewed is still the one."""
        process = self.knowledge.process(process_code, RELEASE)
        releases = self._releases(process)
        base = releases[0] if releases else None
        if (base.number if base else None) != data.base:
            raise ConflictError(
                f"{label(base.number) if base else 'nothing'} is the latest release now: "
                "review the changes again"
            )
        now = _Current(self.session, process)
        if not now.scope:
            raise RuleViolationError("nothing to release: the map has no failure modes yet")
        items, _ = self._items(base, now, process)
        if base is not None and not items:
            raise RuleViolationError(f"nothing changed since {label(base.number)}")
        release = Release(
            process_id=process.id,
            number=next_number(r.number for r in releases),
            note=data.note,
            released_by_user_id=self.principal.user_id,
        )
        self.session.add(release)
        try:
            self.session.flush()
            self.session.add_all(
                ReleaseItem(release_id=release.id, object_type=t, object_id=i, rev=now.revs[t, i])
                for (t, i) in now.scope
            )
            self.session.commit()
        except IntegrityError as error:  # someone released the same number a moment ago
            self.session.rollback()
            raise ConflictError("someone released at the same moment: review again") from error
        return self._out(release)


def _new_box(content: dict[str, Any], boxes: dict[int, Box]) -> str:
    """'New box under Secondary cooling › Spray zones' (the process itself left out)."""
    path: list[str] = []
    at = content.get("parent_id")
    while at is not None and at in boxes and boxes[at].parent_id is not None:
        path.insert(0, boxes[at].name)
        at = boxes[at].parent_id
    return f"New, under {' › '.join(path)}" if path else "New"


def _marker(own: DraftItem | None, items: Iterable[DraftItem], since: str) -> str:
    """The blue dot's text: 'New since v3', 'Control changed since v3', 'Changed since v3'."""
    if own is not None and own.verb is Verb.ADDED:
        return f"New{since}"
    others = [i for i in items if i.object_type is not ObjectType.BOX]
    kinds = {i.object_type for i in others}
    if own is None and len(kinds) == 1:
        verbs = {i.verb for i in others}
        verb = verbs.pop().value if len(verbs) == 1 else "changed"
        return f"{OBJECT_NAMES[kinds.pop()]} {verb}{since}"
    return f"Changed{since}"
