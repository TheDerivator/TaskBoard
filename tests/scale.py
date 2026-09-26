"""A big board for performance checks: thousands of generated tasks on top of the sample board."""

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import Person, Placement, ProjectNode, Section, Task, TaskHelper
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.task_keys import generate_key

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
