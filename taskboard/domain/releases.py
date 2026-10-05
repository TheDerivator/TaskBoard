"""Releases of a process's FMEA and control plan (DESIGN "Versioning" 2-4): what a release freezes
(its scope, and which document shows each object), what changed since the last release (the
draft, computed, never stored), and the warnings shown before releasing.

Pure: works on snapshots of boxes, links and controls taken from the database or rebuilt from a
release's frozen revisions, so the current draft and an old version follow the same rules.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum

from taskboard.domain.knowledge import BoxRole, ObjectType


class Document(StrEnum):
    """FMEA and control plan share one release and one number (DESIGN Versioning 4)."""

    FMEA = "fmea"
    CPL = "cpl"


class Verb(StrEnum):
    ADDED = "added"
    CHANGED = "changed"
    REMOVED = "removed"


type ObjectKey = tuple[ObjectType, int]


@dataclass(frozen=True)
class SnapBox:
    id: int
    process_id: int | None
    parent_id: int | None
    role: BoxRole


@dataclass(frozen=True)
class SnapLink:
    id: int
    from_box_id: int
    to_box_id: int
    leads_to: bool  # the link type has the leads-to role


@dataclass(frozen=True)
class SnapControl:
    id: int
    box_id: int


@dataclass(frozen=True)
class Snapshot:
    """The knowledge objects a process's documents are drawn from (its map, the defects, ...)."""

    boxes: tuple[SnapBox, ...]
    links: tuple[SnapLink, ...]
    controls: tuple[SnapControl, ...]


def _ancestors(box: SnapBox, by_id: Mapping[int, SnapBox]) -> list[int]:
    result: list[int] = []
    at = box.parent_id
    while at is not None and at in by_id and at not in result:
        result.append(at)
        at = by_id[at].parent_id
    return result


def release_scope(process_id: int, snapshot: Snapshot) -> dict[ObjectKey, frozenset[Document]]:
    """What the process's FMEA and control plan show, and which of the two shows each object.

    FMEA: the process's failure modes and every box on the way to one; the leads-to links from
    them to defects or to its other failure modes, those defects (the chips); their controls.
    Control plan: the defects the process's boxes lead to, those causes and every box above them
    (where a cause sits), the leads-to links into the defects, and the causes' controls.
    Everything else is knowledge, versioned per box only (DESIGN Versioning 6).
    """
    by_id = {b.id: b for b in snapshot.boxes}
    docs: dict[ObjectKey, set[Document]] = {}

    def add(object_type: ObjectType, object_id: int, document: Document) -> None:
        docs.setdefault((object_type, object_id), set()).add(document)

    failure_modes = {
        b.id
        for b in snapshot.boxes
        if b.process_id == process_id and b.role is BoxRole.FAILURE_MODE
    }
    for box_id in failure_modes:
        for above in [box_id, *_ancestors(by_id[box_id], by_id)]:
            add(ObjectType.BOX, above, Document.FMEA)
    causes: set[int] = set()
    for link in snapshot.links:
        source = by_id.get(link.from_box_id)
        target = by_id.get(link.to_box_id)
        if not link.leads_to or source is None or target is None:
            continue
        to_defect = target.role is BoxRole.DEFECT
        if source.id in failure_modes and (to_defect or target.id in failure_modes):
            add(ObjectType.LINK, link.id, Document.FMEA)
            add(ObjectType.BOX, target.id, Document.FMEA)
        if source.process_id == process_id and to_defect:
            causes.add(source.id)
            add(ObjectType.LINK, link.id, Document.CPL)
            add(ObjectType.BOX, target.id, Document.CPL)
            for above in [source.id, *_ancestors(source, by_id)]:
                add(ObjectType.BOX, above, Document.CPL)
    for control in snapshot.controls:
        if control.box_id in failure_modes:
            add(ObjectType.CONTROL, control.id, Document.FMEA)
        if control.box_id in causes:
            add(ObjectType.CONTROL, control.id, Document.CPL)
    return {key: frozenset(found) for key, found in docs.items()}


@dataclass(frozen=True)
class DraftItem:
    object_type: ObjectType
    object_id: int
    verb: Verb
    before: int | None  # the released revision
    after: int | None  # the current revision (None: deleted)
    documents: frozenset[Document]


def draft(
    current: Mapping[ObjectKey, tuple[int, frozenset[Document]]],
    released: Mapping[ObjectKey, tuple[int, frozenset[Document]]],
    revisions: Mapping[ObjectKey, int],
    unchanged_since_release: Iterable[ObjectKey] = (),
) -> list[DraftItem]:
    """What a release now would change compared with the last one.

    `current`: the scope now (revision, documents); `released`: the last release's items with the
    documents its frozen state gave them; `revisions`: every existing object's current revision;
    `unchanged_since_release`: objects whose current revision is older than the last release.
    An object that only enters or leaves the documents because of another change (the steps above
    a new failure mode) is no change of its own: the change that moved it is listed instead.
    """
    unchanged = set(unchanged_since_release)
    items: list[DraftItem] = []
    for key, (rev, documents) in current.items():
        if key in released:
            before = released[key][0]
            if before != rev:
                items.append(DraftItem(*key, Verb.CHANGED, before, rev, documents))
        elif key not in unchanged:
            items.append(DraftItem(*key, Verb.ADDED, None, rev, documents))
    for key, (rev, documents) in released.items():
        if key in current or revisions.get(key) == rev:
            continue  # still shown, or left the documents unchanged (another change moved it)
        items.append(DraftItem(*key, Verb.REMOVED, rev, revisions.get(key), documents))
    return sorted(items, key=lambda i: (i.object_type.value, i.object_id))


class ReleaseWarning(StrEnum):
    NO_CONTROLS = "No controls yet: it will appear in the control plan without controls."
    NO_DEFECT = "Leads to no defect: it is in the FMEA but not in the control plan."


def warnings(process_id: int, snapshot: Snapshot) -> dict[int, list[ReleaseWarning]]:
    """What to check before releasing, per box: causes without controls, and failure modes that
    lead to no defect."""
    scope = release_scope(process_id, snapshot)
    controlled = {c.box_id for c in snapshot.controls}
    found: dict[int, list[ReleaseWarning]] = {}
    for box in snapshot.boxes:
        if box.process_id != process_id or box.role is not BoxRole.FAILURE_MODE:
            continue
        in_plan = Document.CPL in scope.get((ObjectType.BOX, box.id), frozenset())
        if not in_plan:
            found.setdefault(box.id, []).append(ReleaseWarning.NO_DEFECT)
        elif box.id not in controlled:
            found.setdefault(box.id, []).append(ReleaseWarning.NO_CONTROLS)
    return found


def next_number(numbers: Iterable[int]) -> int:
    """Releases of a process count v1, v2, ...; FMEA and control plan share the number."""
    return max(numbers, default=0) + 1


def label(number: int) -> str:
    return f"v{number}"
