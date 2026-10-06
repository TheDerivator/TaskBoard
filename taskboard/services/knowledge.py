"""Process-knowledge use cases: a process's map; saving a box with its links, controls and external
links (every change a new revision holding the full content); moving and deleting boxes; history;
references from tasks and changes; the kinds and link types settings.

Rights follow sections (D-080): a map box is in its process's owning section, a defect names its
own. `knowledge.view` reads, `knowledge.edit` edits; a link also needs view rights on its other
end. Kinds and link types need `knowledge.configure` (global).
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import date
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from taskboard.db.ids import in_ids
from taskboard.db.models import (
    Attachment,
    Box,
    BoxKind,
    BoxLink,
    Change,
    Control,
    Department,
    ExternalLink,
    LinkType,
    Person,
    Process,
    Reference,
    Release,
    Revision,
    Section,
    Task,
)
from taskboard.db.text import contains_ci
from taskboard.domain.access import Permission
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    ConflictError,
    NotFoundError,
    RuleViolationError,
    StaleVersionError,
)
from taskboard.domain.knowledge import (
    KIND_STYLES,
    POSITION_GAP,
    BoxRole,
    LinkRole,
    ObjectType,
    ReferenceRole,
    changed_fields,
    check_facts,
    check_field_schema,
    check_fields,
    check_url,
    slugify,
    stable_positions,
    unique_key,
    with_box_param,
)
from taskboard.domain.outline import Outline, TreeNode
from taskboard.domain.task_keys import display_key
from taskboard.identity.principal import Principal
from taskboard.schemas.conversation import AttachmentOut
from taskboard.schemas.knowledge import (
    BoxContent,
    BoxCreate,
    BoxMove,
    BoxOut,
    BoxRef,
    BoxRelated,
    BoxSaved,
    BoxUpdate,
    ControlIn,
    ControlOut,
    ControlPlan,
    ExternalLinkIn,
    ExternalLinkOut,
    FieldDef,
    KindIn,
    KindOut,
    KindUpdate,
    LinkIn,
    LinkOut,
    LinkTypeIn,
    LinkTypeOut,
    LinkTypeUpdate,
    MapGraph,
    MapProcess,
    MapSettings,
    PlanDepartment,
    RelatedChange,
    RelatedTask,
    RevisionOut,
)
from taskboard.services.actors import actor_by_id
from taskboard.services.attachments import AttachmentStore, attachment_out, store_image
from taskboard.services.changes import ChangeService
from taskboard.services.frozen import frozen_state
from taskboard.services.markdown import render_markdown
from taskboard.services.tasks import TaskService, permalink
from taskboard.services.visibility import ensure_usable, visible_changes, visible_tasks

VIEW = Permission.KNOWLEDGE_VIEW
EDIT = Permission.KNOWLEDGE_EDIT


def _external_links(rows: Iterable[ExternalLink], box_key: str) -> list[ExternalLinkOut]:
    return [
        ExternalLinkOut(
            kind=e.kind,
            label=e.label,
            url=e.url,
            pass_box_param=e.pass_box_param,
            href=with_box_param(e.url, box_key) if e.pass_box_param else e.url,
        )
        for e in sorted(rows, key=lambda e: (e.position, e.id))
    ]


def _links_content(rows: Iterable[ExternalLink]) -> list[dict[str, Any]]:
    return [
        {"kind": e.kind.value, "label": e.label, "url": e.url, "pass_box_param": e.pass_box_param}
        for e in sorted(rows, key=lambda e: (e.position, e.id))
    ]


# ---------------------------------------------------------------- revision content
# Shared with the sample-data loader, so every revision has the same shape.


def box_content(session: Session, box: Box) -> dict[str, Any]:
    """Everything about a box, as stored in its revisions (and frozen in releases)."""
    links = session.scalars(select(ExternalLink).where(ExternalLink.box_id == box.id))
    kind = session.get(BoxKind, box.kind_id)
    return {
        "key": box.key,
        "process_id": box.process_id,
        "section_id": box.section_id,
        "parent_id": box.parent_id,
        "position": box.position,
        "kind": kind.key if kind else None,
        "name": box.name,
        "body_md": box.body_md,
        "main_url": box.main_url,
        "facts": [list(f) for f in box.facts],
        "fields": dict(box.fields),
        "step_no": box.step_no,
        "owner_person_id": box.owner_person_id,
        "reviewed_at": box.reviewed_at.isoformat() if box.reviewed_at else None,
        "external_links": _links_content(links),
    }


def link_content(session: Session, link: BoxLink) -> dict[str, Any]:
    link_type = session.get(LinkType, link.type_id)
    return {
        "from_box_id": link.from_box_id,
        "to_box_id": link.to_box_id,
        "type": link_type.key if link_type else None,
        "note_md": link.note_md,
        "fields": dict(link.fields),
    }


def control_content(session: Session, control: Control) -> dict[str, Any]:
    links = session.scalars(select(ExternalLink).where(ExternalLink.control_id == control.id))
    return {
        "box_id": control.box_id,
        "kind": control.kind.value,
        "text": control.text,
        "position": control.position,
        "fields": dict(control.fields),
        "external_links": _links_content(links),
    }


def _new_external_links(items: Sequence[ExternalLinkIn]) -> list[ExternalLink]:
    return [
        ExternalLink(
            kind=item.kind,
            label=item.label,
            url=check_url(item.url) or "",
            pass_box_param=item.pass_box_param,
            position=position,
        )
        for position, item in enumerate(items)
        if check_url(item.url)
    ]


class KnowledgeService:
    def __init__(
        self,
        session: Session,
        principal: Principal,
        *,
        today: date | None = None,
        store: AttachmentStore | None = None,  # for images in descriptions
    ) -> None:
        self.session = session
        self.principal = principal
        self.today = today or date.today()
        self.store = store
        self._process_cache: dict[int, Process] | None = None

    # ------------------------------------------------------------------ rights and lookups

    def _processes(self) -> dict[int, Process]:
        if self._process_cache is None:
            self._process_cache = {p.id: p for p in self.session.scalars(select(Process))}
        return self._process_cache

    def section_of(self, box: Box) -> int:
        if box.process_id is not None:
            return self._processes()[box.process_id].section_id
        if box.section_id is None:  # the database's CHECK makes this impossible
            raise RuleViolationError(f"box {box.key} has neither process nor section")
        return box.section_id

    def _can(self, permission: Permission, box: Box) -> bool:
        return self.principal.can(permission, self.section_of(box))

    def _not_found(self, what: str) -> NotFoundError:
        if self.principal.is_anonymous and self.principal.reach(VIEW).nowhere:
            raise AuthenticationRequiredError("log in to see process knowledge")
        return NotFoundError(what)

    def box(self, key: str, permission: Permission = VIEW) -> Box:
        """A box the principal can see (and, for `permission`, may do that with)."""
        ensure_usable(self.principal)
        box = self.session.scalars(select(Box).where(Box.key == key.strip().lower())).one_or_none()
        if box is None or not self._can(VIEW, box):
            raise self._not_found(f"no box {key}")
        if permission is not VIEW:
            self.principal.require(permission, self.section_of(box))
        return box

    def box_by_id(self, box_id: int) -> Box:
        """A box by its internal id (an image's owner), if the principal can see it."""
        ensure_usable(self.principal)
        box = self.session.get(Box, box_id)
        if box is None or not self._can(VIEW, box):
            raise self._not_found("no such box")
        return box

    def find_boxes(self, query: str, limit: int = 20) -> list[BoxRef]:
        """Boxes whose name or key contains `query` (ignoring case), in every map and catalogue
        the principal can see: the editor's link picker, a change's "Where in the map"."""
        ensure_usable(self.principal)
        needle = query.strip()
        if not needle:
            return []
        rows = self.session.scalars(
            select(Box)
            .where(contains_ci(Box.name, needle) | contains_ci(Box.key, needle))
            .order_by(Box.name, Box.id)
        )
        found = [b.id for b in rows if self._can(VIEW, b)][:limit]
        return self._refs(found)

    def upload(self, key: str, filename: str | None, data: bytes) -> AttachmentOut:
        """An image for the box's description; it stays as long as the box (its history uses it)."""
        box = self.box(key, EDIT)
        if self.store is None:
            raise RuleViolationError("uploads are not available here")
        attachment = store_image(
            self.store, filename, data, box_id=box.id, uploader_user_id=self.principal.user_id
        )
        self.session.add(attachment)
        self.session.commit()
        return attachment_out(attachment)

    def process(self, code: str, permission: Permission = VIEW) -> Process:
        ensure_usable(self.principal)
        process = self.session.scalars(
            select(Process).where(Process.code == code.strip().upper())
        ).one_or_none()
        if process is None or not self.principal.can(VIEW, process.section_id):
            raise self._not_found(f"no process {code}")
        if permission is not VIEW:
            self.principal.require(permission, process.section_id)
        return process

    def _kinds(self) -> dict[str, BoxKind]:
        return {k.key: k for k in self.session.scalars(select(BoxKind))}

    def _kind(self, key: str) -> BoxKind:
        kind = self.session.scalars(select(BoxKind).where(BoxKind.key == key)).one_or_none()
        if kind is None:
            raise NotFoundError(f"no box kind {key}")
        return kind

    def _link_type(self, key: str) -> LinkType:
        link_type = self.session.scalars(select(LinkType).where(LinkType.key == key)).one_or_none()
        if link_type is None:
            raise NotFoundError(f"no link type {key}")
        return link_type

    def _department_sections(self, section_id: int) -> list[int]:
        department = select(Section.department_id).where(Section.id == section_id).scalar_subquery()
        return list(
            self.session.scalars(select(Section.id).where(Section.department_id == department))
        )

    # ------------------------------------------------------------------ output

    def _box_out(self, box: Box, keys: dict[int, str], kinds: dict[int, BoxKind]) -> BoxOut:
        links = self.session.scalars(select(ExternalLink).where(ExternalLink.box_id == box.id))
        return self._box_out_with(box, keys, kinds, list(links))

    def _box_out_with(
        self, box: Box, keys: dict[int, str], kinds: dict[int, BoxKind], links: list[ExternalLink]
    ) -> BoxOut:
        return BoxOut(
            key=box.key,
            process_id=box.process_id,
            section_id=self.section_of(box),
            parent_key=keys.get(box.parent_id) if box.parent_id is not None else None,
            position=box.position,
            kind=kinds[box.kind_id].key,
            name=box.name,
            body_md=box.body_md,
            body_html=render_markdown(box.body_md) if box.body_md else "",
            main_url=box.main_url,
            facts=[[str(k), str(v)] for k, v in box.facts],
            fields=dict(box.fields),
            step_no=box.step_no,
            owner_person_id=box.owner_person_id,
            reviewed_at=box.reviewed_at,
            external_links=_external_links(links, box.key),
            rev=box.rev,
            version=box.version,
        )

    @staticmethod
    def _link_out(link: BoxLink, keys: dict[int, str], types: dict[int, LinkType]) -> LinkOut:
        return LinkOut(
            id=link.id,
            type=types[link.type_id].key,
            from_key=keys[link.from_box_id],
            to_key=keys[link.to_box_id],
            note_md=link.note_md,
            note_html=render_markdown(link.note_md) if link.note_md else "",
            fields=dict(link.fields),
            rev=link.rev,
        )

    @staticmethod
    def _control_out(control: Control, box_key: str, links: list[ExternalLink]) -> ControlOut:
        return ControlOut(
            id=control.id,
            box_key=box_key,
            kind=control.kind,
            text=control.text,
            position=control.position,
            fields=dict(control.fields),
            external_links=_external_links(links, box_key),
            rev=control.rev,
        )

    def _kind_out(self, kind: BoxKind, count: int = 0) -> KindOut:
        return KindOut(
            key=kind.key,
            name=kind.name,
            description=kind.description,
            role=kind.role,
            style=kind.style,
            has_facts=kind.has_facts,
            has_main_url=kind.has_main_url,
            builtin=kind.builtin,
            position=kind.position,
            field_schema=[FieldDef.model_validate(f) for f in kind.field_schema],
            box_count=count,
        )

    @staticmethod
    def _link_type_out(link_type: LinkType, count: int = 0) -> LinkTypeOut:
        return LinkTypeOut(
            key=link_type.key,
            forward_name=link_type.forward_name,
            backward_name=link_type.backward_name,
            description=link_type.description,
            role=link_type.role,
            builtin=link_type.builtin,
            position=link_type.position,
            field_schema=[FieldDef.model_validate(f) for f in link_type.field_schema],
            link_count=count,
        )

    # ------------------------------------------------------------------ the map

    def release_of(self, process: Process, number: int) -> Release:
        """A released version of the process's FMEA and control plan (v3 is number 3)."""
        release = self.session.scalars(
            select(Release).where(Release.process_id == process.id, Release.number == number)
        ).one_or_none()
        if release is None:
            raise NotFoundError(f"{process.name} has no release v{number}")
        return release

    def graph(self, process_code: str, release: int | None = None) -> MapGraph:
        """The process's map, its department's defects, and boxes elsewhere linked to them; with
        `release`, what that version froze (read only)."""
        process = self.process(process_code)
        if release is not None:
            state = frozen_state(self.session, self.release_of(process, release).id)
            map_boxes = [b for b in state.boxes if b.process_id == process.id]
            shown = {b.id: b for b in map_boxes}
            shown |= {b.id: b for b in state.boxes if b.id not in shown and self._can(VIEW, b)}
            links = [lk for lk in state.links if lk.from_box_id in shown and lk.to_box_id in shown]
            controls = sorted(
                (c for c in state.controls if c.box_id in shown), key=lambda c: (c.position, c.id)
            )
            return self._graph_out(
                process, map_boxes, shown, links, controls, (state.box_links, state.control_links)
            )
        map_boxes = list(self.session.scalars(select(Box).where(Box.process_id == process.id)))
        defects = [
            d
            for d in self.session.scalars(
                select(Box).where(
                    Box.process_id.is_(None),
                    Box.section_id.in_(self._department_sections(process.section_id)),
                )
            )
            if self._can(VIEW, d)
        ]
        shown = {b.id: b for b in [*map_boxes, *defects]}
        links = list(
            self.session.scalars(
                select(BoxLink).where(
                    in_ids(BoxLink.from_box_id, shown) | in_ids(BoxLink.to_box_id, shown)
                )
            )
        )
        others = {lk.from_box_id for lk in links} | {lk.to_box_id for lk in links}
        for box in self.session.scalars(select(Box).where(in_ids(Box.id, others - set(shown)))):
            if self._can(VIEW, box):
                shown[box.id] = box
        links = [lk for lk in links if lk.from_box_id in shown and lk.to_box_id in shown]
        controls = list(
            self.session.scalars(
                select(Control)
                .where(
                    in_ids(Control.box_id, [*(b.id for b in map_boxes), *(d.id for d in defects)])
                )
                .order_by(Control.position, Control.id)
            )
        )
        external = self._external_rows(list(shown), controls)
        return self._graph_out(process, map_boxes, shown, links, controls, external, current=True)

    def _graph_out(
        self,
        process: Process,
        map_boxes: list[Box],
        shown: dict[int, Box],
        links: list[BoxLink],
        controls: list[Control],
        external: tuple[dict[int, list[ExternalLink]], dict[int, list[ExternalLink]]],
        *,
        current: bool = False,  # an old version: no change counts, nothing to edit
    ) -> MapGraph:
        section = self.session.get(Section, process.section_id)
        if section is None:
            raise NotFoundError("the process's section is gone")
        box_links, control_links = external
        keys = {b.id: b.key for b in shown.values()}
        kinds = {k.id: k for k in self.session.scalars(select(BoxKind))}
        types = {t.id: t for t in self.session.scalars(select(LinkType))}
        root = next((b for b in map_boxes if b.parent_id is None), None)
        ordered = sorted(
            shown.values(), key=lambda b: (b.process_id != process.id, b.position, b.id)
        )
        return MapGraph(
            process=MapProcess(
                id=process.id,
                code=process.code,
                name=process.name,
                section_id=process.section_id,
                department_id=section.department_id,
            ),
            root_key=root.key if root else None,
            boxes=[self._box_out_with(b, keys, kinds, box_links.get(b.id, [])) for b in ordered],
            links=[self._link_out(lk, keys, types) for lk in links],
            controls=[
                self._control_out(c, keys[c.box_id], control_links.get(c.id, [])) for c in controls
            ],
            kinds=[self._kind_out(k) for k in sorted(kinds.values(), key=lambda k: k.position)],
            link_types=[
                self._link_type_out(t) for t in sorted(types.values(), key=lambda t: t.position)
            ],
            change_counts=self._change_counts([b.id for b in map_boxes], keys) if current else {},
            can_edit=current and self.principal.can(EDIT, process.section_id),
        )

    def _external_rows(
        self, box_ids: list[int], controls: list[Control]
    ) -> tuple[dict[int, list[ExternalLink]], dict[int, list[ExternalLink]]]:
        """The external links of these boxes and of these controls, by owner id."""
        box_links: dict[int, list[ExternalLink]] = {}
        control_links: dict[int, list[ExternalLink]] = {}
        for row in self.session.scalars(
            select(ExternalLink).where(
                in_ids(ExternalLink.box_id, box_ids)
                | in_ids(ExternalLink.control_id, [c.id for c in controls])
            )
        ):
            if row.box_id is not None:
                box_links.setdefault(row.box_id, []).append(row)
            elif row.control_id is not None:
                control_links.setdefault(row.control_id, []).append(row)
        return box_links, control_links

    def _department(self, code: str) -> tuple[Department, list[int]]:
        """A department (by code, ignoring case) where you may read process knowledge somewhere,
        with its sections."""
        wanted = code.strip()
        departments = list(self.session.scalars(select(Department)))
        department = next((d for d in departments if d.code == wanted), None) or next(
            (d for d in departments if d.code.casefold() == wanted.casefold()), None
        )
        sections: list[int] = []
        if department is not None:
            sections = list(
                self.session.scalars(
                    select(Section.id)
                    .where(Section.department_id == department.id)
                    .order_by(Section.id)
                )
            )
        if department is None or not any(self.principal.can(VIEW, s) for s in sections):
            raise self._not_found(f"no department {code}")
        return department, sections

    def control_plan(
        self, department_code: str, process_code: str | None = None, release: int | None = None
    ) -> ControlPlan:
        """A department's defects, the boxes that lead to them in any map you can see, the boxes
        above those causes (where they sit) and the causes' controls: what the CPL view draws.
        With `release` (which needs `process_code`), what that version of the process froze."""
        ensure_usable(self.principal)
        department, sections = self._department(department_code)
        types = {t.id: t for t in self.session.scalars(select(LinkType))}
        leads_to = {t.id for t in types.values() if t.role == LinkRole.LEADS_TO}
        if release is not None:
            if process_code is None:
                raise RuleViolationError("a released control plan is one process's: name it")
            process = self.process(process_code)
            if process.section_id not in sections:
                raise NotFoundError(f"{process.name} is not in {department.name}")
            state = frozen_state(self.session, self.release_of(process, release).id)
            boxes = {b.id: b for b in state.boxes}
            defects = sorted(
                (b for b in state.boxes if b.process_id is None and self._can(VIEW, b)),
                key=lambda b: (b.position, b.id),
            )
            defect_ids = {d.id for d in defects}
            links = [
                lk for lk in state.links if lk.to_box_id in defect_ids and lk.type_id in leads_to
            ]
            causes = [
                boxes[lk.from_box_id]
                for lk in links
                if lk.from_box_id in boxes and boxes[lk.from_box_id].process_id is not None
            ]
            parents = {b.id: b.parent_id for b in state.boxes}
            controls = [c for c in state.controls if c.box_id in {b.id for b in causes}]
            external = (state.box_links, state.control_links)
        else:
            defects = [
                d
                for d in self.session.scalars(
                    select(Box)
                    .where(Box.process_id.is_(None), Box.section_id.in_(sections))
                    .order_by(Box.position, Box.id)
                )
                if self._can(VIEW, d)
            ]
            links = list(
                self.session.scalars(
                    select(BoxLink)
                    .where(
                        in_ids(BoxLink.to_box_id, [d.id for d in defects]),
                        BoxLink.type_id.in_(leads_to),
                    )
                    .order_by(BoxLink.id)
                )
            )
            causes = [
                b
                for b in self.session.scalars(
                    select(Box).where(in_ids(Box.id, {lk.from_box_id for lk in links}))
                )
                if b.process_id is not None and self._can(VIEW, b)
            ]
            parents = dict(
                self.session.execute(
                    select(Box.id, Box.parent_id).where(
                        in_ids(Box.process_id, {b.process_id for b in causes if b.process_id})
                    )
                ).all()
            )
            boxes = {}
            controls = list(
                self.session.scalars(
                    select(Control)
                    .where(in_ids(Control.box_id, {b.id for b in causes}))
                    .order_by(Control.position, Control.id)
                )
            )
            external = None
        causes = list({b.id: b for b in causes}.values())
        cause_ids = {b.id for b in causes}
        links = [lk for lk in links if lk.from_box_id in cause_ids]
        # Where each cause sits: the boxes above it, up to its process's root.
        above: set[int] = set()
        for cause in causes:
            at = parents.get(cause.id)
            while at is not None and at not in above:
                above.add(at)
                at = parents.get(at)
        rest = above - cause_ids
        if release is None:
            boxes = {b.id: b for b in self.session.scalars(select(Box).where(in_ids(Box.id, rest)))}
        in_maps = [*causes, *(boxes[i] for i in rest if i in boxes)]
        shown = [*defects, *sorted(in_maps, key=lambda b: (b.process_id or 0, b.position, b.id))]
        controls = sorted(controls, key=lambda c: (c.position, c.id))
        box_links, control_links = external or self._external_rows([b.id for b in shown], controls)
        keys = {b.id: b.key for b in shown}
        kinds = {k.id: k for k in self.session.scalars(select(BoxKind))}
        return ControlPlan(
            department=PlanDepartment(id=department.id, code=department.code, name=department.name),
            boxes=[self._box_out_with(b, keys, kinds, box_links.get(b.id, [])) for b in shown],
            links=[self._link_out(lk, keys, types) for lk in links],
            controls=[
                self._control_out(c, keys[c.box_id], control_links.get(c.id, [])) for c in controls
            ],
            kinds=[self._kind_out(k) for k in sorted(kinds.values(), key=lambda k: k.position)],
            link_types=[
                self._link_type_out(t) for t in sorted(types.values(), key=lambda t: t.position)
            ],
            defect_sections=[]
            if release is not None
            else [s for s in sections if self.principal.can(EDIT, s)],
        )

    def _change_counts(self, box_ids: list[int], keys: dict[int, str]) -> dict[str, int]:
        """Visible process changes attached to each box (the views roll them up)."""
        if not box_ids or self.principal.reach(Permission.CHANGE_VIEW).nowhere:
            return {}
        changes = visible_changes(select(Change.id), self.principal)
        rows = self.session.execute(
            select(Reference.box_id, func.count())
            .where(in_ids(Reference.box_id, box_ids), Reference.change_id.in_(changes))
            .group_by(Reference.box_id)
        ).all()
        return {keys[box_id]: count for box_id, count in rows}

    def start_map(self, process_code: str) -> BoxOut:
        """The root of a process's map: the process itself, as a process step."""
        process = self.process(process_code, EDIT)
        if self.session.scalar(
            select(Box.id).where(Box.process_id == process.id, Box.parent_id.is_(None))
        ):
            raise ConflictError(f"{process.name} has a map already")
        kind = self.session.scalars(
            select(BoxKind).where(BoxKind.role == BoxRole.STEP).order_by(BoxKind.position)
        ).first()
        if kind is None:
            raise RuleViolationError("there is no kind for process steps")
        box = Box(
            key=self._new_key(process.name),
            process_id=process.id,
            kind_id=kind.id,
            name=process.name,
            facts=[],
            fields={},
        )
        self.session.add(box)
        self.session.flush()
        self._record_box(box)
        self.session.commit()
        return self._box_out(box, {}, {kind.id: kind})

    # ------------------------------------------------------------------ revisions

    def _record(
        self,
        object_type: ObjectType,
        object_id: int,
        box_id: int,
        rev: int,
        content: dict[str, Any],
        *,
        deleted: bool = False,
    ) -> None:
        self.session.add(
            Revision(
                object_type=object_type,
                object_id=object_id,
                box_id=box_id,
                rev=rev,
                content=content,
                deleted=deleted,
                author_user_id=None if self.principal.is_anonymous else self.principal.user_id,
                api_token_id=self.principal.token_id,
            )
        )

    def _box_content(self, box: Box) -> dict[str, Any]:
        return box_content(self.session, box)

    def _record_box(self, box: Box, *, deleted: bool = False) -> None:
        self._record(
            ObjectType.BOX, box.id, box.id, box.rev, self._box_content(box), deleted=deleted
        )

    def _link_content(self, link: BoxLink) -> dict[str, Any]:
        return link_content(self.session, link)

    def _control_content(self, control: Control) -> dict[str, Any]:
        return control_content(self.session, control)

    # ------------------------------------------------------------------ saving boxes

    def _new_key(self, name: str) -> str:
        base = slugify(name)
        taken = self.session.scalars(select(Box.key).where(Box.key.like(f"{base}%")))
        return unique_key(name, taken)

    def _apply(self, box: Box, data: BoxContent, kind: BoxKind) -> None:
        """The box's own fields (not its links and controls), checked."""
        if (
            data.owner_person_id is not None
            and self.session.get(Person, data.owner_person_id) is None
        ):
            raise NotFoundError(f"no person {data.owner_person_id}")
        box.kind_id = kind.id
        box.name = data.name
        box.body_md = data.body_md
        box.main_url = check_url(data.main_url)
        box.facts = check_facts(data.facts)
        box.fields = check_fields(data.fields, kind.field_schema)
        box.step_no = data.step_no or None
        box.owner_person_id = data.owner_person_id
        self.session.execute(delete(ExternalLink).where(ExternalLink.box_id == box.id))
        for link in _new_external_links(data.external_links):
            link.box_id = box.id
            self.session.add(link)
        self.session.flush()

    def create_box(self, data: BoxCreate) -> BoxSaved:
        kind = self._kind(data.kind)
        if kind.role is BoxRole.DEFECT:
            if data.parent_key is not None:
                raise RuleViolationError("defects are not part of a map: they form a catalogue")
            if data.section_id is None or self.session.get(Section, data.section_id) is None:
                raise RuleViolationError("a defect names the section that owns it")
            self.principal.require(EDIT, data.section_id)
            box = Box(process_id=None, section_id=data.section_id, parent_id=None)
            siblings = select(func.max(Box.position)).where(
                Box.process_id.is_(None), Box.section_id == data.section_id
            )
        else:
            if data.parent_key is None:
                raise RuleViolationError("a box goes under another box (or start the map)")
            parent = self.box(data.parent_key, EDIT)
            if parent.process_id is None:
                raise RuleViolationError("defects have no boxes under them")
            box = Box(process_id=parent.process_id, parent_id=parent.id)
            siblings = select(func.max(Box.position)).where(Box.parent_id == parent.id)
        box.key = self._new_key(data.name)
        box.kind_id = kind.id
        box.name = data.name
        box.position = (self.session.scalar(siblings) or 0) + POSITION_GAP
        box.facts, box.fields = [], {}
        self.session.add(box)
        self.session.flush()
        self._apply(box, data, kind)
        if data.before_key is not None and box.parent_id is not None:
            self._place(box, box.parent_id, data.before_key)
        self._record_box(box)
        self._save_links(box, data.links)
        self._save_controls(box, data.controls)
        self.session.commit()
        return self.saved(box.key)

    def update_box(self, key: str, data: BoxUpdate) -> BoxSaved:
        box = self.box(key, EDIT)
        if data.version != box.version:
            raise StaleVersionError("someone else changed this box; reload it")
        kind = self._kind(data.kind)
        current = self.session.get(BoxKind, box.kind_id)
        if current is not None and (current.role is BoxRole.DEFECT) != (
            kind.role is BoxRole.DEFECT
        ):
            raise RuleViolationError("a defect stays a defect, and a map box a map box")
        before = self._box_content(box)
        self._apply(box, data, kind)
        if self._box_content(box) != before:
            box.rev += 1
            self._record_box(box)
        self._save_links(box, data.links)
        self._save_controls(box, data.controls)
        self.session.commit()
        return self.saved(box.key)

    def _save_links(self, box: Box, wanted: Sequence[LinkIn]) -> None:
        """Every link touching the box becomes `wanted`, in both directions (the editor offers
        "leads to" next to "caused by"); kept ones (by id) keep their history. A link's history
        shows on the box it starts from."""
        existing = {
            lk.id: lk
            for lk in self.session.scalars(
                select(BoxLink).where(
                    (BoxLink.from_box_id == box.id) | (BoxLink.to_box_id == box.id)
                )
            )
        }
        plan: list[tuple[LinkIn, LinkType, Box, Box]] = []  # item, type, from, to
        seen: set[tuple[int, int, int]] = set()
        for item in wanted:
            link_type = self._link_type(item.type)
            other = self.box(item.to_key)
            if other.id == box.id:
                raise RuleViolationError("a box cannot link to itself")
            start, end = (box, other) if item.direction == "forward" else (other, box)
            if (start.id, end.id, link_type.id) in seen:
                raise RuleViolationError(f"the link with {other.name} appears twice")
            seen.add((start.id, end.id, link_type.id))
            plan.append((item, link_type, start, end))
        kept = {item.id for item, *_ in plan if item.id in existing}
        for link_id, link in existing.items():
            if link_id not in kept:
                self._record(
                    ObjectType.LINK,
                    link.id,
                    link.from_box_id,
                    link.rev + 1,
                    self._link_content(link),
                    deleted=True,
                )
                self.session.delete(link)
        self.session.flush()
        for item, link_type, start, end in plan:
            fields = check_fields(item.fields, link_type.field_schema)
            if item.id in existing:
                link = existing[item.id]
                before = self._link_content(link)
                link.from_box_id, link.to_box_id, link.type_id = start.id, end.id, link_type.id
                link.note_md, link.fields = item.note_md, fields
                self.session.flush()
                if self._link_content(link) != before:
                    link.rev += 1
                    self._record(
                        ObjectType.LINK, link.id, start.id, link.rev, self._link_content(link)
                    )
            else:
                link = BoxLink(
                    from_box_id=start.id,
                    to_box_id=end.id,
                    type_id=link_type.id,
                    note_md=item.note_md,
                    fields=fields,
                )
                self.session.add(link)
                self.session.flush()
                self._record(ObjectType.LINK, link.id, start.id, link.rev, self._link_content(link))

    def _save_controls(self, box: Box, wanted: Sequence[ControlIn]) -> None:
        """Controls belong to failure modes (later also causes); kept ones (by id) keep their
        history."""
        kind = self.session.get(BoxKind, box.kind_id)
        if wanted and (kind is None or kind.role is not BoxRole.FAILURE_MODE):
            raise RuleViolationError("only failure modes have controls")
        existing = {
            c.id: c for c in self.session.scalars(select(Control).where(Control.box_id == box.id))
        }
        kept = {item.id for item in wanted if item.id in existing}
        for control_id, control in existing.items():
            if control_id not in kept:
                self._remove_control(control)
        # Kept controls keep their place where they can, so their revisions stay meaningful.
        positions = stable_positions(
            [existing[item.id].position if item.id in existing else None for item in wanted]
        )
        for position, item in zip(positions, wanted, strict=True):
            if item.id in existing:
                control = existing[item.id]
                before = self._control_content(control)
            else:
                control = Control(box_id=box.id, kind=item.kind, text=item.text, fields={})
                self.session.add(control)
                self.session.flush()
                before = None
            control.kind, control.text, control.position = item.kind, item.text, position
            control.fields = check_fields(item.fields, [])  # no schema for controls yet
            self.session.execute(delete(ExternalLink).where(ExternalLink.control_id == control.id))
            for link in _new_external_links(item.external_links):
                link.control_id = control.id
                self.session.add(link)
            self.session.flush()
            after = self._control_content(control)
            if before is None:
                self._record(ObjectType.CONTROL, control.id, box.id, control.rev, after)
            elif after != before:
                control.rev += 1
                self._record(ObjectType.CONTROL, control.id, box.id, control.rev, after)

    def _remove_control(self, control: Control) -> None:
        self._record(
            ObjectType.CONTROL,
            control.id,
            control.box_id,
            control.rev + 1,
            self._control_content(control),
            deleted=True,
        )
        self.session.execute(delete(ExternalLink).where(ExternalLink.control_id == control.id))
        self.session.delete(control)
        self.session.flush()

    def saved(self, key: str) -> BoxSaved:
        """A box with its links (both ways) and controls, as the editor shows them."""
        box = self.box(key)
        links = list(
            self.session.scalars(
                select(BoxLink).where(
                    (BoxLink.from_box_id == box.id) | (BoxLink.to_box_id == box.id)
                )
            )
        )
        ends = {lk.from_box_id for lk in links} | {lk.to_box_id for lk in links} | {box.id}
        visible = {
            b.id: b
            for b in self.session.scalars(select(Box).where(in_ids(Box.id, ends)))
            if self._can(VIEW, b)
        }
        if box.parent_id is not None:
            parent = self.session.get(Box, box.parent_id)
            if parent is not None:
                visible[parent.id] = parent
        keys = {b.id: b.key for b in visible.values()}
        kinds = {k.id: k for k in self.session.scalars(select(BoxKind))}
        types = {t.id: t for t in self.session.scalars(select(LinkType))}
        controls = list(
            self.session.scalars(
                select(Control)
                .where(Control.box_id == box.id)
                .order_by(Control.position, Control.id)
            )
        )
        return BoxSaved(
            box=self._box_out(box, keys, kinds),
            links=[
                self._link_out(lk, keys, types)
                for lk in links
                if lk.from_box_id in visible and lk.to_box_id in visible
            ],
            controls=[
                self._control_out(
                    c,
                    box.key,
                    list(
                        self.session.scalars(
                            select(ExternalLink).where(ExternalLink.control_id == c.id)
                        )
                    ),
                )
                for c in controls
            ],
        )

    # ------------------------------------------------------------------ the tree

    def _outline(self, process_id: int) -> Outline[int]:
        rows = self.session.execute(
            select(Box.id, Box.parent_id, Box.position).where(Box.process_id == process_id)
        )
        return Outline(TreeNode(i, p, pos) for i, p, pos in rows)

    def _place(self, box: Box, parent_id: int, before_key: str | None) -> None:
        """Put `box` among `parent_id`'s children, before `before_key` (or last); renumber."""
        siblings = [
            b
            for b in self.session.scalars(
                select(Box).where(Box.parent_id == parent_id).order_by(Box.position, Box.id)
            )
            if b.id != box.id
        ]
        index = len(siblings)
        if before_key is not None:
            found = [i for i, b in enumerate(siblings) if b.key == before_key]
            if not found:
                raise RuleViolationError(f"{before_key} is not under the same box")
            index = found[0]
        order = [*siblings[:index], box, *siblings[index:]]
        positions = stable_positions([None if b.id == box.id else b.position for b in order])
        for sibling, position in zip(order, positions, strict=True):
            if sibling.id == box.id:
                box.position = position
            elif sibling.position != position:
                # Only when the gaps ran out: a real change of the sibling's place, so a revision.
                sibling.position = position
                sibling.rev += 1
                self.session.flush()
                self._record_box(sibling)
        self.session.flush()

    def move_box(self, key: str, data: BoxMove) -> BoxSaved:
        box = self.box(key, EDIT)
        if box.process_id is None:
            raise RuleViolationError("defects have no place in a map")
        if box.parent_id is None:
            raise RuleViolationError("the process itself stays at the top of its map")
        parent = self.box(data.parent_key, EDIT)
        if parent.process_id != box.process_id:
            raise RuleViolationError("a box moves within its own process's map")
        if self._outline(box.process_id).would_create_cycle(box.id, parent.id):
            raise RuleViolationError("a box cannot go under itself or a box below it")
        before = self._box_content(box)
        box.parent_id = parent.id
        self._place(box, parent.id, data.before_key)
        if self._box_content(box) != before:
            box.rev += 1
            self._record_box(box)
        self.session.commit()
        return self.saved(box.key)

    def delete_box(self, key: str) -> None:
        """Only without boxes under it; its links, controls and references go with it."""
        box = self.box(key, EDIT)
        if self.session.scalar(select(func.count()).where(Box.parent_id == box.id)):
            raise ConflictError("move or delete the boxes under it first")
        for link in self.session.scalars(
            select(BoxLink).where((BoxLink.from_box_id == box.id) | (BoxLink.to_box_id == box.id))
        ):
            self._record(
                ObjectType.LINK,
                link.id,
                link.from_box_id,
                link.rev + 1,
                self._link_content(link),
                deleted=True,
            )
            self.session.delete(link)
        for control in self.session.scalars(select(Control).where(Control.box_id == box.id)):
            self._remove_control(control)
        self.session.execute(delete(Reference).where(Reference.box_id == box.id))
        images = list(
            self.session.scalars(select(Attachment.public_id).where(Attachment.box_id == box.id))
        )
        self.session.execute(delete(Attachment).where(Attachment.box_id == box.id))
        self._record(
            ObjectType.BOX, box.id, box.id, box.rev + 1, self._box_content(box), deleted=True
        )
        self.session.execute(delete(ExternalLink).where(ExternalLink.box_id == box.id))
        self.session.flush()
        self.session.delete(box)
        self.session.commit()
        if self.store is not None:
            for public_id in images:
                self.store.delete(public_id)

    def mark_reviewed(self, key: str) -> BoxSaved:
        """The box was checked and is still right (DESIGN: owner and last reviewed date)."""
        box = self.box(key, EDIT)
        if box.reviewed_at != self.today:
            box.reviewed_at = self.today
            box.rev += 1
            self._record_box(box)
        self.session.commit()
        return self.saved(box.key)

    # ------------------------------------------------------------------ history

    def history(self, key: str) -> list[RevisionOut]:
        """The box's revisions, and those of its controls and outgoing links, newest first."""
        box = self.box(key)
        revisions = list(
            self.session.scalars(
                select(Revision).where(Revision.box_id == box.id).order_by(Revision.id)
            )
        )
        previous: dict[tuple[ObjectType, int], dict[str, Any]] = {}
        result: list[RevisionOut] = []
        names = dict(self.session.execute(select(Box.id, Box.name)).all())
        for revision in revisions:
            ident = (revision.object_type, revision.object_id)
            before = previous.get(ident)
            previous[ident] = revision.content
            result.append(
                RevisionOut(
                    object_type=revision.object_type,
                    object_id=revision.object_id,
                    rev=revision.rev,
                    created_at=revision.created_at,
                    author=actor_by_id(
                        self.session, revision.author_user_id, revision.api_token_id
                    ),
                    deleted=revision.deleted,
                    changed=[] if revision.deleted else changed_fields(before, revision.content),
                    summary=self.summary(revision, before, names),
                )
            )
        return list(reversed(result))

    @staticmethod
    def summary(revision: Revision, before: dict[str, Any] | None, names: dict[int, str]) -> str:
        content = revision.content
        verb = "Removed" if revision.deleted else ("Added" if before is None else "Changed")
        if revision.object_type is ObjectType.CONTROL:
            return f"{verb} {content['kind']} control: {content['text']}"
        if revision.object_type is ObjectType.LINK:
            target = names.get(content["to_box_id"], "a box that was deleted")
            return f"{verb} link: {content['type'].replace('_', ' ')} {target}"
        if before is None:
            return "Created"
        if revision.deleted:
            return "Deleted"
        fields = changed_fields(before, content)
        return "Changed " + ", ".join(f.replace("_md", "").replace("_", " ") for f in fields)

    # ------------------------------------------------------------------ references

    def _box_ref(self, box: Box, names: dict[int, tuple[str, int | None]]) -> BoxRef:
        path: list[str] = []
        parent = box.parent_id
        while parent is not None and parent in names:
            name, parent = names[parent]
            path.insert(0, name)
        if box.process_id is not None and path:
            path[0] = self._processes()[box.process_id].name  # the root is the process
        kind = self.session.get(BoxKind, box.kind_id)
        return BoxRef(
            key=box.key,
            name=box.name,
            kind=kind.key if kind else "",
            process_id=box.process_id,
            path=path,
        )

    def _refs(self, box_ids: Iterable[int]) -> list[BoxRef]:
        boxes = [
            b
            for b in self.session.scalars(select(Box).where(in_ids(Box.id, set(box_ids))))
            if self._can(VIEW, b)
        ]
        processes = {b.process_id for b in boxes if b.process_id is not None}
        names = {
            i: (n, p)
            for i, n, p in self.session.execute(
                select(Box.id, Box.name, Box.parent_id).where(in_ids(Box.process_id, processes))
            )
        }
        return sorted((self._box_ref(b, names) for b in boxes), key=lambda r: (r.path, r.name))

    def change_boxes(self, change_key: str) -> list[BoxRef]:
        """Where a change sits in the knowledge map (only the boxes the reader may see)."""
        change = ChangeService(self.session, self.principal).find(change_key)
        if self.principal.reach(VIEW).nowhere:
            return []
        ids = self.session.scalars(select(Reference.box_id).where(Reference.change_id == change.id))
        return self._refs(ids)

    def link_change(self, change_key: str, box_key: str, *, linked: bool = True) -> list[BoxRef]:
        change = ChangeService(self.session, self.principal).find(change_key)
        self.principal.require(Permission.CHANGE_EDIT, change.process.section_id)
        box = self.box(box_key)
        where = (Reference.change_id == change.id, Reference.box_id == box.id)
        exists = self.session.scalar(select(Reference.id).where(*where))
        if linked and exists is None:
            self.session.add(
                Reference(
                    change_id=change.id,
                    box_id=box.id,
                    role=ReferenceRole.AFFECTS,
                    created_by_user_id=self.principal.user_id,
                )
            )
        elif not linked:
            self.session.execute(delete(Reference).where(*where))
        self.session.commit()
        return self.change_boxes(change.key)

    def task_boxes(self, task_key: str) -> list[BoxRef]:
        task = TaskService(self.session, self.principal).find(task_key)
        if self.principal.reach(VIEW).nowhere:
            return []
        ids = self.session.scalars(select(Reference.box_id).where(Reference.task_id == task.id))
        return self._refs(ids)

    def link_task(self, task_key: str, box_key: str, *, linked: bool = True) -> list[BoxRef]:
        task = TaskService(self.session, self.principal).find(task_key)
        self.principal.require(Permission.TASK_EDIT, task.section_id)
        box = self.box(box_key)
        where = (Reference.task_id == task.id, Reference.box_id == box.id)
        exists = self.session.scalar(select(Reference.id).where(*where))
        if linked and exists is None:
            self.session.add(
                Reference(
                    task_id=task.id,
                    box_id=box.id,
                    role=ReferenceRole.RELATED,
                    created_by_user_id=self.principal.user_id,
                )
            )
        elif not linked:
            self.session.execute(delete(Reference).where(*where))
        self.session.commit()
        return self.task_boxes(task.key)

    def related(self, box_key: str) -> BoxRelated:
        """Process changes on this box or any box below it (DESIGN rule 8), and tasks about it."""
        box = self.box(box_key)
        branch = {box.id}
        if box.process_id is not None:
            branch = self._outline(box.process_id).subtree(box.id)
        keys = dict(
            self.session.execute(select(Box.id, Box.key).where(in_ids(Box.id, branch))).all()
        )
        changes: list[RelatedChange] = []
        if not self.principal.reach(Permission.CHANGE_VIEW).nowhere:
            rows = self.session.execute(
                select(Change, Reference.box_id)
                .join(Reference, Reference.change_id == Change.id)
                .where(
                    in_ids(Reference.box_id, branch),
                    Change.id.in_(visible_changes(select(Change.id), self.principal)),
                )
            ).all()
            attached: dict[int, int] = {}
            for change, box_id in rows:
                attached.setdefault(change.id, box_id)
            unique = {change.id: change for change, _ in rows}
            summaries = ChangeService(self.session, self.principal, today=self.today).summaries(
                list(unique.values())
            )
            changes = [
                RelatedChange(
                    key=s.key,
                    title=s.title,
                    url=s.url,
                    state=s.state.state.value,
                    state_date=s.state.date,
                    box_key=keys[attached[c.id]],
                )
                for c, s in zip(unique.values(), summaries, strict=True)
            ]
        tasks: list[RelatedTask] = []
        if not self.principal.reach(Permission.TASK_VIEW).nowhere:
            query = visible_tasks(
                select(Task)
                .join(Reference, Reference.task_id == Task.id)
                .where(Reference.box_id == box.id),
                self.principal,
            )
            tasks = [
                RelatedTask(key=t.key, ref=display_key(t.key), title=t.title, url=permalink(t.key))
                for t in self.session.scalars(query.order_by(Task.rank))
            ]
        return BoxRelated(changes=sorted(changes, key=lambda c: c.key), tasks=tasks)

    # ------------------------------------------------------------------ settings

    def settings(self) -> MapSettings:
        ensure_usable(self.principal)
        if self.principal.reach(VIEW).nowhere:
            raise self._not_found("no process knowledge to see")
        kind_counts = Counter(self.session.scalars(select(Box.kind_id)))
        type_counts = Counter(self.session.scalars(select(BoxLink.type_id)))
        kinds = self.session.scalars(select(BoxKind).order_by(BoxKind.position, BoxKind.id))
        types = self.session.scalars(select(LinkType).order_by(LinkType.position, LinkType.id))
        return MapSettings(
            kinds=[self._kind_out(k, kind_counts[k.id]) for k in kinds],
            link_types=[self._link_type_out(t, type_counts[t.id]) for t in types],
            can_configure=self.principal.can(Permission.KNOWLEDGE_CONFIGURE),
        )

    def _configure(self) -> None:
        ensure_usable(self.principal)
        self.principal.require(Permission.KNOWLEDGE_CONFIGURE)

    @staticmethod
    def _settings_key(key: str | None, name: str) -> str:
        return key or slugify(name).replace("-", "_")[:40] or "custom"

    def create_kind(self, data: KindIn) -> MapSettings:
        self._configure()
        key = self._settings_key(data.key, data.name)
        if self.session.scalar(select(BoxKind.id).where(BoxKind.key == key)):
            raise ConflictError(f"a kind {key} exists")
        if data.style not in KIND_STYLES:
            raise RuleViolationError(f"style is one of {', '.join(KIND_STYLES)}")
        last = self.session.scalar(select(func.max(BoxKind.position))) or 0
        self.session.add(
            BoxKind(
                key=key,
                name=data.name,
                description=data.description,
                role=BoxRole.PLAIN,
                style=data.style,
                has_facts=data.has_facts,
                has_main_url=data.has_main_url,
                position=last + 1,
                field_schema=check_field_schema(f.model_dump() for f in data.field_schema),
            )
        )
        self.session.commit()
        return self.settings()

    def update_kind(self, key: str, data: KindUpdate) -> MapSettings:
        self._configure()
        kind = self._kind(key)
        if data.style is not None and data.style not in KIND_STYLES:
            raise RuleViolationError(f"style is one of {', '.join(KIND_STYLES)}")
        for field in ("name", "description", "style", "has_facts", "has_main_url", "position"):
            value = getattr(data, field)
            if value is not None:
                setattr(kind, field, value)
        if data.field_schema is not None:
            kind.field_schema = check_field_schema(f.model_dump() for f in data.field_schema)
        self.session.commit()
        return self.settings()

    def delete_kind(self, key: str) -> MapSettings:
        self._configure()
        kind = self._kind(key)
        if kind.builtin:
            raise RuleViolationError("built-in kinds cannot be deleted (rename them instead)")
        if self.session.scalar(select(func.count()).where(Box.kind_id == kind.id)):
            raise ConflictError("boxes of this kind exist; give them another kind first")
        self.session.delete(kind)
        self.session.commit()
        return self.settings()

    def create_link_type(self, data: LinkTypeIn) -> MapSettings:
        self._configure()
        key = self._settings_key(data.key, data.forward_name)
        if self.session.scalar(select(LinkType.id).where(LinkType.key == key)):
            raise ConflictError(f"a link type {key} exists")
        last = self.session.scalar(select(func.max(LinkType.position))) or 0
        self.session.add(
            LinkType(
                key=key,
                forward_name=data.forward_name,
                backward_name=data.backward_name,
                description=data.description,
                role=LinkRole.PLAIN,
                position=last + 1,
                field_schema=check_field_schema(f.model_dump() for f in data.field_schema),
            )
        )
        self.session.commit()
        return self.settings()

    def update_link_type(self, key: str, data: LinkTypeUpdate) -> MapSettings:
        self._configure()
        link_type = self._link_type(key)
        for field in ("forward_name", "backward_name", "description", "position"):
            value = getattr(data, field)
            if value is not None:
                setattr(link_type, field, value)
        if data.field_schema is not None:
            link_type.field_schema = check_field_schema(f.model_dump() for f in data.field_schema)
        self.session.commit()
        return self.settings()

    def delete_link_type(self, key: str) -> MapSettings:
        self._configure()
        link_type = self._link_type(key)
        if link_type.builtin:
            raise RuleViolationError("built-in link types cannot be deleted (rename them instead)")
        if self.session.scalar(select(func.count()).where(BoxLink.type_id == link_type.id)):
            raise ConflictError("links of this type exist; remove them first")
        self.session.delete(link_type)
        self.session.commit()
        return self.settings()
