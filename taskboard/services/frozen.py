"""A release's frozen state: the boxes, links, controls and external links it froze, rebuilt from
their revisions as unsaved objects, so an old version is drawn like the current one; and the
snapshot the release rules (domain/releases.py) work on, for current or frozen objects."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Box,
    BoxKind,
    BoxLink,
    Control,
    ExternalLink,
    LinkType,
    ReleaseItem,
    Revision,
)
from taskboard.domain.knowledge import BoxRole, ControlKind, ExternalLinkKind, LinkRole, ObjectType
from taskboard.domain.releases import ObjectKey, SnapBox, SnapControl, SnapLink, Snapshot


@dataclass
class FrozenState:
    """Unsaved copies of what a release froze (never add them to a session)."""

    boxes: list[Box] = field(default_factory=list[Box])
    links: list[BoxLink] = field(default_factory=list[BoxLink])
    controls: list[Control] = field(default_factory=list[Control])
    box_links: dict[int, list[ExternalLink]] = field(default_factory=dict[int, list[ExternalLink]])
    control_links: dict[int, list[ExternalLink]] = field(
        default_factory=dict[int, list[ExternalLink]]
    )
    revisions: dict[ObjectKey, Revision] = field(default_factory=dict[ObjectKey, Revision])


def _external_links(items: Iterable[dict[str, Any]], **owner: int) -> list[ExternalLink]:
    return [
        ExternalLink(
            id=position,
            kind=ExternalLinkKind(e["kind"]),
            label=e["label"],
            url=e["url"],
            pass_box_param=e["pass_box_param"],
            position=position,
            **owner,
        )
        for position, e in enumerate(items)
    ]


def frozen_state(session: Session, release_id: int) -> FrozenState:
    """Everything a release froze, as it was. A kind or link type removed since then is shown as
    a plain one (the box keeps its name and content)."""
    items = list(session.scalars(select(ReleaseItem).where(ReleaseItem.release_id == release_id)))
    wanted = {(i.object_type, i.object_id): i.rev for i in items}
    state = FrozenState()
    for object_type in ObjectType:
        ids = [object_id for (t, object_id) in wanted if t is object_type]
        if not ids:
            continue
        for revision in session.scalars(
            select(Revision).where(
                Revision.object_type == object_type, in_ids(Revision.object_id, ids)
            )
        ):
            if wanted[object_type, revision.object_id] == revision.rev:
                state.revisions[object_type, revision.object_id] = revision
    kinds = {k.key: k for k in session.scalars(select(BoxKind))}
    plain_kind = next(iter(sorted(kinds.values(), key=lambda k: k.position)), None)
    types = {t.key: t for t in session.scalars(select(LinkType))}
    for (object_type, object_id), revision in sorted(state.revisions.items()):
        content = revision.content
        if object_type is ObjectType.BOX:
            kind = kinds.get(content["kind"]) or plain_kind
            reviewed = content.get("reviewed_at")
            state.boxes.append(
                Box(
                    id=object_id,
                    key=content["key"],
                    process_id=content["process_id"],
                    section_id=content["section_id"],
                    parent_id=content["parent_id"],
                    position=content["position"],
                    kind_id=kind.id if kind else 0,
                    name=content["name"],
                    body_md=content["body_md"],
                    main_url=content["main_url"],
                    facts=content["facts"],
                    fields=content["fields"],
                    step_no=content["step_no"],
                    owner_person_id=content["owner_person_id"],
                    reviewed_at=date.fromisoformat(reviewed) if reviewed else None,
                    rev=revision.rev,
                    version=revision.rev,
                )
            )
            state.box_links[object_id] = _external_links(
                content["external_links"], box_id=object_id
            )
        elif object_type is ObjectType.LINK:
            link_type = types.get(content["type"])
            if link_type is None:
                continue  # its type is gone: nothing to call it by
            state.links.append(
                BoxLink(
                    id=object_id,
                    from_box_id=content["from_box_id"],
                    to_box_id=content["to_box_id"],
                    type_id=link_type.id,
                    note_md=content["note_md"],
                    fields=content["fields"],
                    rev=revision.rev,
                )
            )
        else:
            state.controls.append(
                Control(
                    id=object_id,
                    box_id=content["box_id"],
                    kind=ControlKind(content["kind"]),
                    text=content["text"],
                    position=content["position"],
                    fields=content["fields"],
                    rev=revision.rev,
                )
            )
            state.control_links[object_id] = _external_links(
                content["external_links"], control_id=object_id
            )
    return state


def snapshot(
    boxes: Iterable[Box],
    links: Iterable[BoxLink],
    controls: Iterable[Control],
    kinds: Mapping[int, BoxKind],
    types: Mapping[int, LinkType],
) -> Snapshot:
    """The release rules' view of these objects: tree, roles, leads-to links, controls' boxes."""
    return Snapshot(
        boxes=tuple(
            SnapBox(
                b.id,
                b.process_id,
                b.parent_id,
                kinds[b.kind_id].role if b.kind_id in kinds else BoxRole.PLAIN,
            )
            for b in boxes
        ),
        links=tuple(
            SnapLink(
                lk.id,
                lk.from_box_id,
                lk.to_box_id,
                lk.type_id in types and types[lk.type_id].role == LinkRole.LEADS_TO,
            )
            for lk in links
        ),
        controls=tuple(SnapControl(c.id, c.box_id) for c in controls),
    )


def snapshot_of_revisions(
    revisions: Iterable[Revision],
    kinds: Mapping[str, BoxKind],
    types: Mapping[str, LinkType],
) -> Snapshot:
    """The release rules' view of objects as their revisions hold them (kinds and link types by
    key): the knowledge as it was at some moment, e.g. for the sample's past releases."""
    boxes: list[SnapBox] = []
    links: list[SnapLink] = []
    controls: list[SnapControl] = []
    for revision in revisions:
        c = revision.content
        if revision.object_type is ObjectType.BOX:
            kind = kinds.get(c["kind"])
            role = kind.role if kind else BoxRole.PLAIN
            boxes.append(SnapBox(revision.object_id, c["process_id"], c["parent_id"], role))
        elif revision.object_type is ObjectType.LINK:
            link_type = types.get(c["type"])
            leads_to = link_type is not None and link_type.role == LinkRole.LEADS_TO
            links.append(SnapLink(revision.object_id, c["from_box_id"], c["to_box_id"], leads_to))
        else:
            controls.append(SnapControl(revision.object_id, c["box_id"]))
    return Snapshot(tuple(boxes), tuple(links), tuple(controls))
