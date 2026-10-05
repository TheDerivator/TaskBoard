"""A big board for performance checks: thousands of tasks, process changes and map boxes."""

import random
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Box,
    BoxKind,
    BoxLink,
    Change,
    ChangePeriod,
    Control,
    LinkType,
    Person,
    Placement,
    Post,
    Process,
    ProjectNode,
    Revision,
    Section,
    Task,
    TaskHelper,
    User,
)
from taskboard.domain.changes import PeriodKind
from taskboard.domain.knowledge import POSITION_GAP, ControlKind, ObjectType
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.task_keys import generate_key
from taskboard.services.knowledge import box_content, control_content, link_content

SCALE_TODAY = date(2026, 10, 3)

WORDS = [
    "coating",
    "adhesion",
    "roll",
    "grinding",
    "furnace",
    "sensor",
    "audit",
    "supplier",
    "recipe",
    "defect",
    "vibration",
    "calibration",
    "trial",
    "report",
    "spectroscopy",
    "maintenance",
    "scrap",
    "yield",
    "line",
    "cooling",
]


def add_tasks(session: Session, count: int, seed: int = 7) -> None:
    """Append `count` tasks at the bottom of the ranking, with helpers and a project placement."""
    rng = random.Random(seed)
    people = list(session.scalars(select(Person.id).where(Person.active.is_(True))))
    sections = list(session.scalars(select(Section.id)))
    nodes = list(session.execute(select(ProjectNode.project_id, ProjectNode.id)))
    rank = session.scalar(select(func.max(Task.rank))) or 0
    keys = set(session.scalars(select(Task.key)))
    statuses = list(TaskStatus)
    for i in range(1, count + 1):
        key = generate_key(rng.choice)
        while key in keys:
            key = generate_key(rng.choice)
        keys.add(key)
        lead = rng.choice(people)
        project_id, node_id = rng.choice(nodes)
        words = " ".join(rng.sample(WORDS, 4))
        session.add(
            Task(
                key=key,
                title=f"Generated {i}: {words}",
                description=f"Look into {words}. " * rng.randint(1, 6),
                rank=rank + i,
                status=rng.choice(statuses),
                lead_person_id=lead,
                section_id=rng.choice(sections),
                helpers=[
                    TaskHelper(person_id=p)
                    for p in rng.sample([p for p in people if p != lead], rng.randint(0, 2))
                ],
                placements=[Placement(project_id=project_id, node_id=node_id)],
            )
        )
    session.commit()


def add_changes(session: Session, process_code: str, count: int, seed: int = 11) -> None:
    """`count` process changes for a process, numbered after its last one: each with one to three
    periods (tests and permanent changes over the last year, each posted) and a comment."""
    rng = random.Random(seed)
    process = session.scalars(select(Process).where(Process.code == process_code)).one()
    number = session.scalar(select(func.max(Change.number)).where(Change.process_id == process.id))
    people = list(session.scalars(select(Person.id).where(Person.active.is_(True))))
    users = list(session.scalars(select(User.id).where(User.person_id.is_not(None))))
    for i in range(1, count + 1):
        n = (number or 0) + i
        words = " ".join(rng.sample(WORDS, 3))
        change = Change(
            key=f"{process_code}-{n:02d}",
            number=n,
            process_id=process.id,
            title=f"Generated change {n}: {words}",
            what_md=f"Change the {words} settings.",
            why_md=f"Fewer defects from {rng.choice(WORDS)}.",
            owner_person_id=rng.choice(people),
        )
        session.add(change)
        session.flush()
        for _ in range(rng.randint(1, 3)):
            start = SCALE_TODAY - timedelta(days=rng.randint(0, 365))
            test = rng.random() < 0.6
            post = Post(change_id=change.id, author_user_id=rng.choice(users), body_md="Period.")
            session.add(post)
            session.flush()
            session.add(
                ChangePeriod(
                    post_id=post.id,
                    change_id=change.id,
                    kind=PeriodKind.TEST if test else PeriodKind.CHANGE,
                    start_date=start,
                    end_date=start + timedelta(days=rng.randint(0, 20)) if test else None,
                    label="Test" if test else "Process change",
                    scope_tags=[rng.choice(WORDS).capitalize(), f"Line {rng.randint(1, 3)}"],
                )
            )
        session.add(
            Post(change_id=change.id, author_user_id=rng.choice(users), body_md=f"About {words}.")
        )
    session.commit()


def add_map(session: Session, process_code: str, count: int, seed: int = 13) -> None:
    """About `count` more boxes in a process's map: 20 zones of 5 steps each, holding failure
    modes (each leading to one of the department's defects, with controls) and knowledge boxes;
    every box, link and control with its first revision."""
    rng = random.Random(seed)
    process = session.scalars(select(Process).where(Process.code == process_code)).one()
    kinds = {k.key: k for k in session.scalars(select(BoxKind))}
    leads_to = session.scalars(select(LinkType).where(LinkType.key == "leads_to")).one()
    defects = list(session.scalars(select(Box.id).where(Box.process_id.is_(None))))
    root = session.scalars(
        select(Box).where(Box.process_id == process.id, Box.parent_id.is_(None))
    ).one()
    boxes: list[Box] = []
    links: list[BoxLink] = []
    controls: list[Control] = []

    def box(key: str, parent: Box, kind: str, name: str, position: int) -> Box:
        made = Box(
            key=key,
            process_id=process.id,
            parent_id=parent.id,
            position=POSITION_GAP * (100 + position),
            kind_id=kinds[kind].id,
            name=name,
            body_md=f"Generated {kind}: {' '.join(rng.sample(WORDS, 5))}.",
        )
        session.add(made)
        session.flush()
        boxes.append(made)
        return made

    leaves = max(count - 120, 0)
    n = 0
    for z in range(20):
        zone = box(f"gen-zone-{z}", root, "step", f"Zone {z} {rng.choice(WORDS)}", z)
        for s_ in range(5):
            step = box(f"gen-step-{z}-{s_}", zone, "step", f"Step {z}.{s_}", s_)
            for leaf in range(leaves // 100 + (1 if z * 5 + s_ < leaves % 100 else 0)):
                n += 1
                if leaf % 3 == 0:
                    fm = box(f"gen-fm-{n}", step, "fm", f"Failure {n} {rng.choice(WORDS)}", leaf)
                    links.append(
                        BoxLink(
                            from_box_id=fm.id, to_box_id=rng.choice(defects), type_id=leads_to.id
                        )
                    )
                    for c in range(rng.randint(1, 2)):
                        controls.append(
                            Control(
                                box_id=fm.id,
                                kind=ControlKind.PREVENT if c == 0 else ControlKind.DETECT,
                                text=f"Check {rng.choice(WORDS)} every shift",
                                position=POSITION_GAP * (c + 1),
                            )
                        )
                else:
                    box(f"gen-know-{n}", step, "know", f"Note {n} on {rng.choice(WORDS)}", leaf)
    session.add_all([*links, *controls])
    session.flush()
    session.add_all(
        [
            *(
                Revision(
                    object_type=ObjectType.BOX,
                    object_id=b.id,
                    box_id=b.id,
                    rev=1,
                    content=box_content(session, b),
                )
                for b in boxes
            ),
            *(
                Revision(
                    object_type=ObjectType.LINK,
                    object_id=lk.id,
                    box_id=lk.from_box_id,
                    rev=1,
                    content=link_content(session, lk),
                )
                for lk in links
            ),
            *(
                Revision(
                    object_type=ObjectType.CONTROL,
                    object_id=c.id,
                    box_id=c.box_id,
                    rev=1,
                    content=control_content(session, c),
                )
                for c in controls
            ),
        ]
    )
    session.commit()
