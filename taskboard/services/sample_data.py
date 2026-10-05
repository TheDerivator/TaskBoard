"""Load the design's sample data (departments, people, projects, tasks, posts, processes, process
changes, the Continuous casting map and the defect catalogue) into an empty board.

The sample is set on 3 Oct 2026 (`SAMPLE_TODAY`). Loaded with another `today`, the process
changes' dates move by the difference, so a demo shows tests running and changes planned.

Each sample person also gets a user account (e.g. `anna.claes`) linked to their person record,
with *Editor* rights on their own department. Accounts can log in only when a demo password is
given. Used for demos (`python -m taskboard seed --sample`) and by the tests.
"""

import json
import struct
import unicodedata
import zlib
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Attachment,
    Box,
    BoxKind,
    BoxLink,
    Change,
    ChangePeriod,
    Control,
    Department,
    Event,
    ExternalLink,
    LinkType,
    Person,
    Placement,
    Post,
    Process,
    Project,
    ProjectNode,
    Reference,
    Release,
    ReleaseItem,
    Revision,
    Role,
    RoleAssignment,
    Section,
    Task,
    TaskHelper,
    User,
)
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.domain.changes import PeriodKind, normalize_tags, period_label
from taskboard.domain.events import EventKind
from taskboard.domain.knowledge import (
    POSITION_GAP,
    ControlKind,
    ExternalLinkKind,
    ObjectType,
    ReferenceRole,
)
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.releases import release_scope
from taskboard.domain.task_keys import normalize_key
from taskboard.identity.passwords import hash_password
from taskboard.services.attachments import AttachmentStore, new_public_id
from taskboard.services.frozen import snapshot_of_revisions
from taskboard.services.knowledge import box_content, control_content, link_content
from taskboard.services.markdown import ATTACHMENT_URL_PREFIX

SAMPLE_FILE = Path(__file__).resolve().parent / "data" / "sample-data.json"
SAMPLE_IMAGE_LINK = "uploads/defect-map-line2.png"  # as written in the sample posts
SAMPLE_TODAY = date(2026, 10, 3)  # "today" in the design's sample data and mockups
SAMPLE_DEFECT_SECTION = "Quality"  # the design's defects have no owner; Quality keeps the catalogue

# What the knowledge mockups (ProcessMap, DefectView) show beyond sample-data.json.
SAMPLE_BOX_TEXTS: dict[str, str] = {
    "plan": "Restrictions planning must respect when building casting sequences. Each rule says "
    "what it protects against.",
    "ref-powder": "Supplier datasheets: viscosity, melting point and basicity per powder type.",
    "k-osc": "The mould moves up and down so the shell does not stick. Stroke and frequency set "
    "the depth of the oscillation marks.\n\n- Negative strip time: the mould moves down faster "
    "than the strand\n- Settings depend on casting speed",
    "mould": "Forms the first solid shell. Most of the slab's surface quality is decided in the "
    "first seconds here.",
    "fm-powder": "Liquid powder is dragged into the shell when the flow near the meniscus is too "
    "strong or the powder is too fluid.",
    "fm-clog": "Alumina builds up in the nozzle, makes the flow asymmetric, then breaks loose and "
    "causes a level jump.",
    "fm-osc": "Cracks start in the bottom of deep oscillation marks.",
    "d-sliver": "Thin lines along the rolling direction on the strip surface. Mould powder or "
    "inclusions trapped just under the slab surface get stretched out during hot and cold rolling.",
    "d-blisters": "Raised bubbles on the strip surface, often after annealing or coating.",
    "d-incl": "Non-metallic particles inside the steel.",
    "d-trans": "Cracks across the casting direction, usually at the slab corners or in the "
    "oscillation marks.",
    "d-long": "Cracks along the casting direction, mostly in the slab centre.",
    "d-corner": "Cracks at slab corners.",
    "d-edge": "Damage at the slab ends.",
}
SAMPLE_DEFECT_GROUPS = {
    "d-sliver": "Surface",
    "d-blisters": "Surface",
    "d-incl": "Internal",
    "d-trans": "Cracks",
    "d-long": "Cracks",
    "d-corner": "Cracks",
    "d-edge": "Other",
}

# What the GlobalSearch mockup finds in a task's description beyond sample-data.json.
SAMPLE_TASK_TEXTS = {
    "T-117": "Visual acceptance limits for class A surfaces, signed off by both sides. "
    "Mould powder residues on class A surfaces get a limit of their own.",
}

# The knowledge's history (M18): the map is drawn in November 2025; v2 adds oscillation and
# cutting; after v3 come the four changes of the FmeaMap mockup's draft. Each entry: sample id →
# (when, who). Edited objects also say what they held before the edit.
SAMPLE_MAP_DRAWN = datetime(2025, 11, 10, 9, 0)
SAMPLE_ADDED: dict[str, tuple[datetime, str]] = {
    "m-osc": (datetime(2026, 2, 16, 10, 0), "BP"),
    "k-osc": (datetime(2026, 2, 16, 10, 5), "BP"),
    "fm-osc": (datetime(2026, 2, 16, 10, 10), "BP"),
    "L8": (datetime(2026, 2, 16, 10, 12), "BP"),
    "cut": (datetime(2026, 2, 18, 14, 0), "FM"),
    "cut-torch": (datetime(2026, 2, 18, 14, 5), "FM"),
    "fm-burr": (datetime(2026, 2, 18, 14, 10), "FM"),
    "L11": (datetime(2026, 2, 18, 14, 12), "FM"),
    "C4": (datetime(2026, 9, 25, 11, 0), "CM"),
    "L12": (datetime(2026, 9, 28, 15, 30), "AC"),
    "fm-spray": (datetime(2026, 10, 1, 9, 15), "FM"),
    "L9": (datetime(2026, 10, 1, 9, 20), "FM"),
}
SAMPLE_EDITED: dict[str, tuple[datetime, str, dict[str, Any]]] = {
    "fm-powder": (
        datetime(2026, 6, 2, 10, 0),
        "CM",
        {"body_md": "Liquid powder is dragged into the shell when the flow is too strong."},
    ),
    "C3": (
        datetime(2026, 9, 22, 8, 40),
        "DW",
        {"text": "Alarm above [OLD LIMIT] mm fluctuation; affected slabs flagged for inspection"},
    ),
}
SAMPLE_RELEASE_TIME = time(16, 0)

# What the change mockups (ChangeDetail, ChangeConversation) show beyond sample-data.json.
SAMPLE_CHANGE_EXTRAS: dict[str, dict[str, Any]] = {
    "LM-07": {
        "what": "Argon flow during trim additions from [OLD FLOW] to [NEW FLOW] for "
        "ultra-low-carbon grades.",
        "posted": ["2026-04-10T15:20", "2026-04-15T09:40", "2026-04-18T16:10"],
        "comments": [
            (
                "DW",
                "2026-04-14T13:05",
                "Heat 41233 had a delayed argon start, I'd exclude it. "
                "Process data: `ladle-data-14apr.xlsx`",
            ),
            (
                "CM",
                "2026-04-17T11:22",
                "Inclusion counts on both test days look good. Report: `QA-report-0417.pdf`",
            ),
        ],
    },
}


def username_for(name: str) -> str:
    """`Chloé Martens` → `chloe.martens`."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return ".".join(ascii_name.lower().split())


def load_sample_data(
    session: Session,
    *,
    demo_password: str | None = None,
    path: Path = SAMPLE_FILE,
    store: AttachmentStore | None = None,
    today: date | None = None,
) -> bool:
    """Load the sample into an empty board. Returns False (and changes nothing) if tasks exist.

    With a `store`, the sample post's defect map becomes a real (generated) image attachment.
    With a `today`, process changes are moved in time so the sample's 3 Oct 2026 is that day.
    """
    if session.scalar(select(func.count()).select_from(Task)):
        return False
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    sections = _load_org(session, data["departments"])
    people = _load_people(session, data["people"], sections)
    users = _load_users(session, people, demo_password)
    projects, nodes = _load_projects(session, data["projects"], data["project_nodes"])
    tasks = _load_tasks(session, data["tasks"], people, sections)
    processes = _load_processes(session, data["processes"], sections)
    shift = (today - SAMPLE_TODAY) if today else timedelta()
    changes = _load_changes(session, data, processes, people, users, shift)
    _load_knowledge(session, data, processes, sections, people, users, tasks, changes, shift)
    for p in data["placements"]:
        node = nodes[p["node_id"]] if p["node_id"] else None
        session.add(
            Placement(
                task_id=tasks[p["task_id"]].id,
                project_id=projects[p["project_id"]].id,
                node_id=node.id if node else None,
            )
        )
    for p in data["posts"]:
        post = Post(
            task_id=tasks[p["task_id"]].id,
            author_user_id=users[p["author"]].id,
            created_at=_timestamp(p["created_at"]),
            body_md=p["body_md"],
            is_update=p["is_update"],
        )
        session.add(post)
        if store is not None and SAMPLE_IMAGE_LINK in post.body_md:
            session.flush()
            _attach_defect_map(session, store, post)
    for e in data["events"]:
        if e["type"] == "status":
            session.add(
                Event(
                    task_id=tasks[e["task_id"]].id,
                    actor_user_id=users[e["actor"]].id,
                    created_at=_timestamp(e["created_at"]),
                    kind=EventKind.STATUS_CHANGED,
                    data={"from": e["from"], "to": e["to"]},
                )
            )
    session.flush()
    return True


def _attach_defect_map(session: Session, store: AttachmentStore, post: Post) -> None:
    public_id = new_public_id()
    filename = "defect-map-line2.png"
    image = defect_map_png()
    store.save(public_id, image)
    session.add(
        Attachment(
            public_id=public_id,
            task_id=post.task_id,
            post_id=post.id,
            uploader_user_id=post.author_user_id,
            filename=filename,
            content_type="image/png",
            size=len(image),
            created_at=post.created_at,
        )
    )
    post.body_md = post.body_md.replace(
        SAMPLE_IMAGE_LINK, f"{ATTACHMENT_URL_PREFIX}{public_id}/{filename}"
    )


def defect_map_png(width: int = 520, height: int = 200) -> bytes:
    """A bar chart of weekly defect counts (weeks 26-38, a spike after the 4 Sep roll change)."""
    counts = [3, 4, 3, 5, 4, 3, 4, 5, 4, 5, 13, 15, 12]
    ground, bar, spike, axis = (251, 250, 247), (148, 142, 132), (196, 86, 28), (207, 202, 193)
    slot = width // len(counts)
    rows = bytearray()
    for y in range(height):
        rows.append(0)  # PNG filter: none
        for x in range(width):
            week, offset = divmod(x, slot)
            bar_height = counts[min(week, len(counts) - 1)] * (height - 30) // max(counts)
            in_bar = 8 <= offset < slot - 8 and height - 10 - bar_height <= y < height - 10
            color = ground
            if y == height - 10:
                color = axis
            elif in_bar:
                color = spike if counts[min(week, len(counts) - 1)] > 10 else bar
            rows += bytes(color)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        crc = zlib.crc32(tag + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


SAMPLE_TIMEZONE = timezone(timedelta(hours=2))  # the sample's times are Belgian summer time


def _timestamp(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=SAMPLE_TIMEZONE).astimezone(UTC)


def _load_org(
    session: Session, departments: dict[str, list[str]]
) -> dict[tuple[str, str], Section]:
    sections: dict[tuple[str, str], Section] = {}
    for d_pos, (code, section_names) in enumerate(departments.items()):
        department = Department(code=code, name=code, position=d_pos)
        session.add(department)
        for s_pos, name in enumerate(section_names):
            section = Section(department=department, name=name, position=s_pos)
            session.add(section)
            sections[code, name] = section
    session.flush()
    return sections


# The design gives processes a department only; their changes and maps are owned by this section.
SAMPLE_PROCESS_SECTION = "Process"


def _load_processes(
    session: Session, rows: list[dict[str, Any]], sections: dict[tuple[str, str], Section]
) -> dict[str, Process]:
    processes: dict[str, Process] = {}
    for position, row in enumerate(rows):
        process = Process(
            code=row["id"],
            name=row["name"],
            section=sections[row["department"], SAMPLE_PROCESS_SECTION],
            position=position,
        )
        session.add(process)
        processes[row["id"]] = process
    session.flush()
    return processes


def _load_changes(
    session: Session,
    data: dict[str, Any],
    processes: dict[str, Process],
    people: dict[str, Person],
    users: dict[str, User],
    shift: timedelta,
) -> dict[str, Change]:
    """The changes, each period as a post in the change's conversation, and the mockups' extras."""
    periods: dict[str, list[dict[str, Any]]] = {}
    for row in data["change_periods"]:
        periods.setdefault(row["change_id"], []).append(row)
    latest_post = datetime.combine(SAMPLE_TODAY - timedelta(days=1), time(15, 20))
    changes: dict[str, Change] = {}
    for row in data["changes"]:
        key: str = row["id"]
        extras = SAMPLE_CHANGE_EXTRAS.get(key, {})
        posts: list[tuple[str, datetime, str, dict[str, Any] | None]] = []
        for index, period in enumerate(periods.get(key, [])):
            start = date.fromisoformat(period["start_date"])
            posted = extras.get("posted", [])
            written = (
                datetime.fromisoformat(posted[index])
                if index < len(posted)
                else min(datetime.combine(start - timedelta(days=3), time(15, 20)), latest_post)
            )
            posts.append((period["author"] or row["owner"], written, period["body_md"], period))
        for author, written, body in extras.get("comments", []):
            posts.append((author, datetime.fromisoformat(written), body, None))
        posts.sort(key=lambda p: p[1])
        first = posts[0][1] if posts else latest_post
        change = Change(
            key=key,
            number=int(key.rsplit("-", 1)[1]),
            process=processes[row["process_id"]],
            title=row["title"],
            what_md=extras.get("what", ""),
            why_md=row["why"],
            owner_person_id=people[row["owner"]].id,
            created_by_user_id=users[row["owner"]].id,
            created_at=_sample_time(first - timedelta(hours=1), shift),
        )
        session.add(change)
        session.flush()
        for author, written, body, period in posts:
            post = Post(
                change_id=change.id,
                author_user_id=users[author].id,
                created_at=_sample_time(written, shift),
                body_md=body,
            )
            session.add(post)
            if period is None:
                continue
            session.flush()
            end = period["end_date"]
            kind = PeriodKind.TEST if end else PeriodKind.CHANGE
            session.add(
                ChangePeriod(
                    post_id=post.id,
                    change_id=change.id,
                    kind=kind,
                    start_date=date.fromisoformat(period["start_date"]) + shift,
                    end_date=date.fromisoformat(end) + shift if end else None,
                    label=period_label(kind, period["label"]),
                    scope_tags=normalize_tags(period["scope_tags"]),
                )
            )
        changes[key] = change
    session.flush()
    return changes


def _load_knowledge(
    session: Session,
    data: dict[str, Any],
    processes: dict[str, Process],
    sections: dict[tuple[str, str], Section],
    people: dict[str, Person],
    users: dict[str, User],
    tasks: dict[str, Task],
    changes: dict[str, Change],
    shift: timedelta,
) -> None:
    """The map of Continuous casting, the STL defects, their links, controls and external links,
    what refers to them, their dated history and releases (kinds and link types are built in)."""
    kinds = {k.key: k for k in session.scalars(select(BoxKind))}
    link_types = {t.key: t for t in session.scalars(select(LinkType))}
    boxes: dict[str, Box] = {}
    positions: dict[str | None, int] = {}
    for row in data["boxes"]:
        process = processes[row["process_id"]] if row["process_id"] else None
        siblings = row["parent_id"] or f"catalogue:{row['process_id']}"
        positions[siblings] = positions.get(siblings, 0) + 1
        fields = (
            {"group": SAMPLE_DEFECT_GROUPS[row["id"]]} if row["id"] in SAMPLE_DEFECT_GROUPS else {}
        )
        box = Box(
            key=row["id"],
            process_id=process.id if process else None,
            section_id=None if process else sections["STL", SAMPLE_DEFECT_SECTION].id,
            position=positions[siblings] * POSITION_GAP,
            kind_id=kinds[row["kind_id"]].id,
            name=row["name"],
            body_md=row["body_md"] or SAMPLE_BOX_TEXTS.get(row["id"], ""),
            main_url=row["main_url"],
            facts=[[str(k), str(v)] for k, v in dict(row["facts"] or {}).items()],
            fields=fields,
            step_no=row["step_no"],
            owner_person_id=people[row["owner"]].id if row["owner"] else None,
            reviewed_at=date.fromisoformat(row["reviewed_at"]) + shift
            if row["reviewed_at"]
            else None,
        )
        if row["parent_id"]:  # the sample lists parents before their children
            box.parent_id = boxes[row["parent_id"]].id
        session.add(box)
        session.flush()  # one root per map: a box needs its parent from the start
        boxes[row["id"]] = box

    links = [
        BoxLink(
            from_box_id=boxes[row["from_box"]].id,
            to_box_id=boxes[row["to_box"]].id,
            type_id=link_types[row["type_id"]].id,
            note_md=row["note_md"],
            fields=row["fields"],
        )
        for row in data["links"]
    ]
    session.add_all(links)
    controls: dict[str, Control] = {}
    counts: dict[str, int] = {}
    for row in data["controls"]:
        counts[row["box_id"]] = counts.get(row["box_id"], 0) + 1
        control = Control(
            box_id=boxes[row["box_id"]].id,
            kind=ControlKind(row["type"]),
            text=row["text"],
            position=counts[row["box_id"]] * POSITION_GAP,
            fields=row["fields"],
        )
        session.add(control)
        controls[row["id"]] = control
    session.flush()
    for position, row in enumerate(data["external_links"]):
        owner_box = boxes[row["owner_id"]].id if row["owner_type"] == "box" else None
        owner_control = controls[row["owner_id"]].id if row["owner_type"] == "control" else None
        session.add(
            ExternalLink(
                box_id=owner_box,
                control_id=owner_control,
                kind=ExternalLinkKind(row["kind"]),
                label=row["label"],
                url=row["url"],
                pass_box_param=row["pass_box_param"],
                position=position,
            )
        )
    for row in data["references"]:
        is_change = row["source_type"] == "change"
        session.add(
            Reference(
                change_id=changes[row["source_id"]].id if is_change else None,
                task_id=None if is_change else tasks[row["source_id"]].id,
                box_id=boxes[row["box_id"]].id,
                role=ReferenceRole.AFFECTS if is_change else ReferenceRole.RELATED,
            )
        )
    session.flush()

    def author(person: Person | None) -> int | None:
        code = next((c for c, p in people.items() if p is person), None)
        return users[code].id if code else None

    def owner_of(box_id: int) -> int | None:
        box = session.get(Box, box_id)
        return author(
            session.get(Person, box.owner_person_id) if box and box.owner_person_id else None
        )

    objects: list[tuple[str, ObjectType, int, int, dict[str, Any], Box | BoxLink | Control]] = [
        (key, ObjectType.BOX, box.id, box.id, box_content(session, box), box)
        for key, box in boxes.items()
    ]
    objects += [
        (row["id"], ObjectType.LINK, link.id, link.from_box_id, link_content(session, link), link)
        for row, link in zip(data["links"], links, strict=True)
    ]
    objects += [
        (key, ObjectType.CONTROL, c.id, c.box_id, control_content(session, c), c)
        for key, c in controls.items()
    ]
    revisions: list[Revision] = []
    for key, object_type, object_id, box_id, content, row in objects:
        when, by = SAMPLE_ADDED.get(key, (SAMPLE_MAP_DRAWN, ""))
        first = {
            "object_type": object_type,
            "object_id": object_id,
            "box_id": box_id,
            "created_at": _sample_time(when, shift),
            "author_user_id": users[by].id if by else owner_of(box_id),
        }
        if key in SAMPLE_EDITED:
            edited, editor, before = SAMPLE_EDITED[key]
            revisions.append(Revision(rev=1, content=content | before, **first))
            revisions.append(
                Revision(
                    object_type=object_type,
                    object_id=object_id,
                    box_id=box_id,
                    rev=2,
                    content=content,
                    created_at=_sample_time(edited, shift),
                    author_user_id=users[editor].id,
                )
            )
            row.rev = 2
        else:
            revisions.append(Revision(rev=1, content=content, **first))
    session.add_all(revisions)
    session.flush()
    _load_releases(session, data, processes, users, revisions, shift)


def _load_releases(
    session: Session,
    data: dict[str, Any],
    processes: dict[str, Process],
    users: dict[str, User],
    revisions: list[Revision],
    shift: timedelta,
) -> None:
    """v1, v2 and v3 as real releases: what the release rules took from the history at the time
    (the sample's approvers are dropped: there is no approval step, D-081)."""
    kinds = {k.key: k for k in session.scalars(select(BoxKind))}
    types = {t.key: t for t in session.scalars(select(LinkType))}
    for row in data["releases"]:
        process = processes[row["process_id"]]
        when = _sample_time(
            datetime.combine(date.fromisoformat(row["approved_at"]), SAMPLE_RELEASE_TIME), shift
        )
        state: dict[tuple[ObjectType, int], Revision] = {}
        for revision in sorted(revisions, key=lambda r: r.rev):
            if revision.created_at <= when:
                state[revision.object_type, revision.object_id] = revision
        scope = release_scope(process.id, snapshot_of_revisions(state.values(), kinds, types))
        release = Release(
            process_id=process.id,
            number=int(row["number"].removeprefix("v")),
            note=row["note"],
            released_by_user_id=users[row["created_by"]].id,
            released_at=when,
        )
        session.add(release)
        session.flush()
        session.add_all(
            ReleaseItem(release_id=release.id, object_type=t, object_id=i, rev=state[t, i].rev)
            for (t, i) in scope
        )
    session.flush()


def _sample_time(local: datetime, shift: timedelta) -> datetime:
    """A sample time (Belgian, naive) as UTC, moved by `shift`."""
    return local.replace(tzinfo=SAMPLE_TIMEZONE).astimezone(UTC) + shift


def _load_people(
    session: Session, rows: list[dict[str, Any]], sections: dict[tuple[str, str], Section]
) -> dict[str, Person]:
    people: dict[str, Person] = {}
    for row in rows:
        person = Person(
            code=row["code"],
            name=row["name"],
            color=row["color"],
            section=sections[row["department"], row["section"]],
        )
        session.add(person)
        people[row["code"]] = person
    session.flush()
    return people


def _load_users(
    session: Session, people: dict[str, Person], demo_password: str | None
) -> dict[str, User]:
    editor = session.scalars(select(Role).where(Role.key == BuiltinRole.EDITOR.value)).one()
    password_hash = hash_password(demo_password) if demo_password else None
    users: dict[str, User] = {}
    for code, person in people.items():
        user = User(
            username=username_for(person.name),
            display_name=person.name,
            person=person,
            password_hash=password_hash,
        )
        assignment = RoleAssignment(role=editor)
        assignment.scope = Scope.department(person.section.department_id)
        user.assignments.append(assignment)
        session.add(user)
        users[code] = user
    session.flush()
    return users


def _load_projects(
    session: Session, project_rows: list[dict[str, Any]], node_rows: list[dict[str, Any]]
) -> tuple[dict[str, Project], dict[str, ProjectNode]]:
    projects = {
        row["id"]: Project(key=row["id"], name=row["name"], color=row["color"], position=pos)
        for pos, row in enumerate(project_rows)
    }
    session.add_all(projects.values())
    session.flush()
    nodes: dict[str, ProjectNode] = {}
    for row in node_rows:  # parents come before children in the file
        node = ProjectNode(
            project_id=projects[row["project_id"]].id,
            parent_id=nodes[row["parent_id"]].id if row["parent_id"] else None,
            position=row["position"],
            name=row["name"],
        )
        session.add(node)
        session.flush()
        nodes[row["id"]] = node
    return projects, nodes


def _load_tasks(
    session: Session,
    rows: list[dict[str, Any]],
    people: dict[str, Person],
    sections: dict[tuple[str, str], Section],
) -> dict[str, Task]:
    tasks: dict[str, Task] = {}
    for row in sorted(rows, key=lambda r: r["rank"]):
        task = Task(
            key=normalize_key(row["id"]),
            title=row["title"],
            description=SAMPLE_TASK_TEXTS.get(row["id"], row["description"]),
            rank=row["rank"],
            status=TaskStatus(row["status"]),
            lead=people[row["lead"]],
            section=sections[row["department"], row["section"]],
            helpers=[TaskHelper(person=people[code]) for code in row["helpers"]],
        )
        session.add(task)
        tasks[row["id"]] = task
    session.flush()
    return tasks
