"""The design's sample board loads completely and consistently."""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Event,
    Person,
    Placement,
    Post,
    Project,
    ProjectNode,
    Task,
    User,
)
from taskboard.db.session import Database
from taskboard.domain.outline import Outline, TreeNode
from taskboard.domain.task_keys import normalize_key
from taskboard.services.sample_data import SAMPLE_FILE, load_sample_data, username_for

SAMPLE = json.loads(SAMPLE_FILE.read_text(encoding="utf-8"))


def _count(session: Session, model: type) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_everything_is_loaded(sample_database: Database) -> None:
    with sample_database.session() as s:
        assert _count(s, Task) == len(SAMPLE["tasks"]) == 11
        assert _count(s, Person) == len(SAMPLE["people"])
        assert _count(s, Project) == len(SAMPLE["projects"])
        assert _count(s, ProjectNode) == len(SAMPLE["project_nodes"])
        assert _count(s, Placement) == len(SAMPLE["placements"])
        assert _count(s, Post) == len(SAMPLE["posts"])
        assert _count(s, Event) == len(SAMPLE["events"])


def test_ranks_are_dense_and_follow_the_sample(sample_database: Database) -> None:
    with sample_database.session() as s:
        keys = list(s.scalars(select(Task.key).order_by(Task.rank)))
        ranks = list(s.scalars(select(Task.rank).order_by(Task.rank)))
    expected = [normalize_key(t["id"]) for t in sorted(SAMPLE["tasks"], key=lambda t: t["rank"])]
    assert keys == expected
    assert ranks == list(range(1, 12))


def test_outline_numbers_from_the_database_match_the_sample(sample_database: Database) -> None:
    with sample_database.session() as s:
        for project in s.scalars(select(Project)):
            nodes = list(s.scalars(select(ProjectNode).where(ProjectNode.project_id == project.id)))
            outline = Outline(TreeNode(n.id, n.parent_id, n.position) for n in nodes)
            numbers = sorted(outline.number(n.id) for n in nodes)
            expected = sorted(
                n["number"] for n in SAMPLE["project_nodes"] if n["project_id"] == project.key
            )
            assert numbers == expected


def test_sample_people_get_linked_accounts_with_unicode_names(sample_database: Database) -> None:
    with sample_database.session() as s:
        chloe = s.scalars(select(User).where(User.username == "chloe.martens")).one()
        assert chloe.person and chloe.person.name == "Chloé Martens"
        assert chloe.password_hash is None  # no demo password given: cannot log in
        assert [a.role.key for a in chloe.assignments] == ["editor"]
        assert chloe.assignments[0].scope_key.startswith("department:")


def test_loading_twice_is_refused(sample_database: Database) -> None:
    with sample_database.session(write=True) as s:
        assert load_sample_data(s) is False
        assert _count(s, Task) == 11


def test_username_for_strips_accents() -> None:
    assert username_for("Chloé  Martens") == "chloe.martens"
