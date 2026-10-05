"""Release rules (milestone M18): the scope of a release, the draft since the last one, warnings."""

from dataclasses import replace

from hypothesis import given
from hypothesis import strategies as st

from taskboard.domain.knowledge import BoxRole, ObjectType
from taskboard.domain.releases import (
    Document,
    ObjectKey,
    ReleaseWarning,
    SnapBox,
    SnapControl,
    SnapLink,
    Snapshot,
    Verb,
    draft,
    label,
    next_number,
    release_scope,
    warnings,
)

BOX, LINK, CONTROL = ObjectType.BOX, ObjectType.LINK, ObjectType.CONTROL
FMEA, CPL = Document.FMEA, Document.CPL
P, OTHER = 10, 20

# A small map of process P: the process (1) with Mould (2) holding two failure modes (3 leads to
# the defect Sliver, 6 leads to 3) and a knowledge box (4); Cutting (5) has no failure mode.
# Another process has a failure mode (200) leading to Sliver too.
SNAPSHOT = Snapshot(
    boxes=(
        SnapBox(1, P, None, BoxRole.STEP),
        SnapBox(2, P, 1, BoxRole.STEP),
        SnapBox(3, P, 2, BoxRole.FAILURE_MODE),
        SnapBox(4, P, 2, BoxRole.KNOWLEDGE),
        SnapBox(5, P, 1, BoxRole.STEP),
        SnapBox(6, P, 2, BoxRole.FAILURE_MODE),
        SnapBox(100, None, None, BoxRole.DEFECT),
        SnapBox(101, None, None, BoxRole.DEFECT),
        SnapBox(200, OTHER, None, BoxRole.FAILURE_MODE),
    ),
    links=(
        SnapLink(1000, 3, 100, leads_to=True),
        SnapLink(1001, 6, 3, leads_to=True),
        SnapLink(1002, 4, 3, leads_to=False),
        SnapLink(1003, 200, 100, leads_to=True),
    ),
    controls=(SnapControl(500, 3), SnapControl(501, 6), SnapControl(502, 200)),
)


def _with_revs(
    scope: dict[ObjectKey, frozenset[Document]], revs: dict[ObjectKey, int] | None = None
) -> dict[ObjectKey, tuple[int, frozenset[Document]]]:
    return {key: ((revs or {}).get(key, 1), docs) for key, docs in scope.items()}


def test_what_a_release_holds_and_which_document_shows_it() -> None:
    assert release_scope(P, SNAPSHOT) == {
        (BOX, 1): {FMEA, CPL},
        (BOX, 2): {FMEA, CPL},
        (BOX, 3): {FMEA, CPL},
        (BOX, 6): {FMEA},  # leads to a failure mode only: not a cause in the control plan
        (BOX, 100): {FMEA, CPL},
        (LINK, 1000): {FMEA, CPL},
        (LINK, 1001): {FMEA},
        (CONTROL, 500): {FMEA, CPL},
        (CONTROL, 501): {FMEA},
    }
    # The other process's release holds its own cause and the shared defect.
    assert set(release_scope(OTHER, SNAPSHOT)) == {
        (BOX, 200),
        (BOX, 100),
        (LINK, 1003),
        (CONTROL, 502),
    }


def test_right_after_a_release_the_draft_is_empty() -> None:
    scope = _with_revs(release_scope(P, SNAPSHOT))
    revisions = {key: rev for key, (rev, _) in scope.items()}
    assert draft(scope, scope, revisions) == []


def test_an_edit_in_scope_is_in_the_draft_a_knowledge_edit_is_not() -> None:
    released = _with_revs(release_scope(P, SNAPSHOT))
    current = _with_revs(release_scope(P, SNAPSHOT), {(CONTROL, 500): 2})
    revisions = {key: rev for key, (rev, _) in current.items()} | {(BOX, 4): 3}  # 4 edited twice
    [item] = draft(current, released, revisions)
    assert (item.object_type, item.object_id, item.verb) == (CONTROL, 500, Verb.CHANGED)
    assert (item.before, item.after, item.documents) == (1, 2, {FMEA, CPL})


def test_a_new_failure_mode_brings_its_steps_without_counting_them() -> None:
    released = _with_revs(release_scope(P, SNAPSHOT))
    grown = replace(
        SNAPSHOT,
        boxes=(*SNAPSHOT.boxes, SnapBox(7, P, 5, BoxRole.FAILURE_MODE)),
        links=(*SNAPSHOT.links, SnapLink(1004, 7, 101, leads_to=True)),
    )
    current = _with_revs(release_scope(P, grown))
    revisions = {key: rev for key, (rev, _) in current.items()}
    items = draft(current, released, revisions, unchanged_since_release=[(BOX, 5), (BOX, 101)])
    assert [(i.object_type, i.object_id, i.verb) for i in items] == [
        (BOX, 7, Verb.ADDED),
        (LINK, 1004, Verb.ADDED),
    ]


def test_deleting_a_failure_mode_removes_it_with_its_link_and_control() -> None:
    released = _with_revs(release_scope(P, SNAPSHOT))
    shrunk = Snapshot(
        boxes=tuple(b for b in SNAPSHOT.boxes if b.id != 6),
        links=tuple(lk for lk in SNAPSHOT.links if lk.id != 1001),
        controls=tuple(c for c in SNAPSHOT.controls if c.id != 501),
    )
    current = _with_revs(release_scope(P, shrunk))
    revisions = {key: rev for key, (rev, _) in current.items()}
    items = draft(current, released, revisions)
    assert [(i.object_type, i.object_id, i.verb, i.after) for i in items] == [
        (BOX, 6, Verb.REMOVED, None),
        (CONTROL, 501, Verb.REMOVED, None),
        (LINK, 1001, Verb.REMOVED, None),
    ]


def test_warnings_before_releasing() -> None:
    assert warnings(P, SNAPSHOT) == {6: [ReleaseWarning.NO_DEFECT]}
    bare = replace(SNAPSHOT, controls=())
    assert warnings(P, bare) == {3: [ReleaseWarning.NO_CONTROLS], 6: [ReleaseWarning.NO_DEFECT]}


def test_version_numbers() -> None:
    assert next_number([]) == 1 and next_number([1, 3, 2]) == 4
    assert label(4) == "v4"


# ---------------------------------------------------------------- properties

ROLES = [BoxRole.STEP, BoxRole.FAILURE_MODE, BoxRole.KNOWLEDGE, BoxRole.RULE]


@st.composite
def snapshots(draw: st.DrawFn) -> Snapshot:
    """A random map of process P (each box under an earlier one), defects and random links."""
    size = draw(st.integers(min_value=1, max_value=12))
    boxes = [SnapBox(1, P, None, BoxRole.STEP)]
    for box_id in range(2, size + 1):
        parent = draw(st.integers(min_value=1, max_value=box_id - 1))
        boxes.append(SnapBox(box_id, P, parent, draw(st.sampled_from(ROLES))))
    defects = [SnapBox(100 + i, None, None, BoxRole.DEFECT) for i in range(draw(st.integers(0, 3)))]
    ids = [b.id for b in [*boxes, *defects]]
    pairs = draw(
        st.lists(st.tuples(st.sampled_from(ids), st.sampled_from(ids), st.booleans()), max_size=10)
    )
    links = tuple(SnapLink(1000 + i, a, b, lt) for i, (a, b, lt) in enumerate(pairs) if a != b)
    owners = draw(st.lists(st.sampled_from(ids), max_size=6))
    controls = tuple(SnapControl(500 + i, owner) for i, owner in enumerate(owners))
    return Snapshot((*boxes, *defects), links, controls)


@given(snapshots())
def test_a_scope_holds_whole_paths_and_whole_links(snapshot: Snapshot) -> None:
    scope = release_scope(P, snapshot)
    boxes = {b.id: b for b in snapshot.boxes}
    for (object_type, object_id), documents in scope.items():
        assert documents
        if object_type is BOX and boxes[object_id].parent_id is not None:
            assert (BOX, boxes[object_id].parent_id) in scope  # the way up is shown too
        if object_type is LINK:
            link = next(lk for lk in snapshot.links if lk.id == object_id)
            assert (BOX, link.from_box_id) in scope and (BOX, link.to_box_id) in scope
        if object_type is CONTROL:
            control = next(c for c in snapshot.controls if c.id == object_id)
            assert (BOX, control.box_id) in scope


@given(snapshots(), st.data())
def test_the_draft_lists_exactly_the_objects_whose_revision_moved(
    snapshot: Snapshot, data: st.DataObject
) -> None:
    released = _with_revs(release_scope(P, snapshot))
    assert draft(released, released, {k: r for k, (r, _) in released.items()}) == []
    edited = data.draw(st.sets(st.sampled_from(sorted(released, key=str)))) if released else set()
    current = {k: (rev + 1 if k in edited else rev, docs) for k, (rev, docs) in released.items()}
    items = draft(current, released, {k: r for k, (r, _) in current.items()})
    assert {(i.object_type, i.object_id) for i in items} == edited
    assert all(i.verb is Verb.CHANGED for i in items)
