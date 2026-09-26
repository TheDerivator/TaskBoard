"""Load the design's sample data (departments, people, projects, tasks, posts) into an empty board.

Each sample person also gets a user account (e.g. `anna.claes`) linked to their person record,
with *Editor* rights on their own department. Accounts can log in only when a demo password is
given. Used for demos (`python -m taskboard seed --sample`) and by the tests.
"""

import json
import struct
import unicodedata
import zlib
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Attachment,
    Department,
    Event,
    Person,
    Placement,
    Post,
    Project,
    ProjectNode,
    Role,
    RoleAssignment,
    Section,
    Task,
    TaskHelper,
    User,
)
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.domain.events import EventKind
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.task_keys import normalize_key
from taskboard.identity.passwords import hash_password
from taskboard.services.attachments import AttachmentStore, new_public_id
from taskboard.services.markdown import ATTACHMENT_URL_PREFIX

SAMPLE_FILE = Path(__file__).resolve().parent / "data" / "sample-data.json"
SAMPLE_IMAGE_LINK = "uploads/defect-map-line2.png"  # as written in the sample posts


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
) -> bool:
    """Load the sample into an empty board. Returns False (and changes nothing) if tasks exist.

    With a `store`, the sample post's defect map becomes a real (generated) image attachment.
    """
    if session.scalar(select(func.count()).select_from(Task)):
        return False
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    sections = _load_org(session, data["departments"])
    people = _load_people(session, data["people"], sections)
    users = _load_users(session, people, demo_password)
    projects, nodes = _load_projects(session, data["projects"], data["project_nodes"])
    tasks = _load_tasks(session, data["tasks"], people, sections)
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
            description=row["description"],
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
