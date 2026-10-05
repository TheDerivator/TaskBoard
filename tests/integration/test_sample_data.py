"""The design's sample board loads completely and consistently."""

import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.config import Settings
from taskboard.db.models import (
    Box,
    BoxLink,
    Change,
    ChangePeriod,
    Control,
    Department,
    Event,
    ExternalLink,
    Person,
    Placement,
    Post,
    Process,
    Project,
    ProjectNode,
    Reference,
    Section,
    Task,
    User,
)
from taskboard.db.session import Database
from taskboard.domain.outline import Outline, TreeNode
from taskboard.domain.task_keys import normalize_key
from taskboard.services.sample_data import SAMPLE_FILE, load_sample_data, username_for
from tests.helpers import assert_revisions_match_rows

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
        task_posts = select(func.count()).where(Post.task_id.is_not(None))
        assert s.scalar(task_posts) == len(SAMPLE["posts"])
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


def test_the_sample_is_the_designs(sample_database: Database) -> None:
    """The loader's copy of the sample data stays the design's file (one source of truth)."""
    del sample_database
    design = SAMPLE_FILE.parents[3] / "team-tasks-design" / "sample-data.json"
    assert json.loads(design.read_text(encoding="utf-8")) == SAMPLE


def test_processes_are_owned_by_the_process_section(sample_database: Database) -> None:
    with sample_database.session() as s:
        rows = s.execute(
            select(Process.code, Section.name, Department.code)
            .join(Section, Section.id == Process.section_id)
            .join(Department, Department.id == Section.department_id)
            .order_by(Process.position)
        ).all()
    assert [tuple(r) for r in rows] == [
        ("CV", "Process", "STL"),
        ("LM", "Process", "STL"),
        ("CC", "Process", "STL"),
    ]


def test_process_changes_and_their_periods(sample_database: Database) -> None:
    """Every period is a post in its change's conversation; LM-07 also has the mockup's comments."""
    with sample_database.session() as s:
        assert _count(s, Change) == len(SAMPLE["changes"]) == 14
        assert _count(s, ChangePeriod) == len(SAMPLE["change_periods"]) == 24
        lm07 = s.scalars(select(Change).where(Change.key == "LM-07")).one()
        posts = s.scalars(select(Post).where(Post.change_id == lm07.id).order_by(Post.created_at))
        authors = [p.author.username for p in posts]
        assert authors == [
            "anna.claes",  # test, 14 Apr
            "dries.wouters",
            "anna.claes",  # follow-up test, 16 Apr
            "chloe.martens",
            "anna.claes",  # the process change, from 21 Apr
        ]
        kinds = s.scalars(
            select(ChangePeriod.kind)
            .where(ChangePeriod.change_id == lm07.id)
            .order_by(ChangePeriod.start_date)
        )
        assert [k.value for k in kinds] == ["test", "test", "change"]
        assert lm07.what_md.startswith("Argon flow during trim additions")


def test_a_demo_loaded_later_keeps_its_changes_current(settings: Settings) -> None:
    """Loaded ten days after the sample's 3 Oct 2026, every change date moves ten days along."""
    database = Database(settings.resolved_database_url)
    with database.session(write=True) as s:
        assert load_sample_data(s, today=date(2026, 10, 13))
    with database.session() as s:
        lm12 = s.scalars(select(Change).where(Change.key == "LM-12")).one()
        start = s.scalar(select(ChangePeriod.start_date).where(ChangePeriod.change_id == lm12.id))
        assert start == date(2026, 10, 23)
        posted = s.scalar(select(func.min(Post.created_at)).where(Post.change_id == lm12.id))
        assert posted is not None and posted.date() == date(2026, 10, 12)  # still before today
    database.dispose()


def test_the_continuous_casting_map_and_the_defect_catalogue(sample_database: Database) -> None:
    with sample_database.session() as s:
        assert _count(s, Box) == len(SAMPLE["boxes"]) == 37
        assert _count(s, BoxLink) == len(SAMPLE["links"]) == 17
        assert _count(s, Control) == len(SAMPLE["controls"]) == 9
        assert _count(s, ExternalLink) == len(SAMPLE["external_links"]) == 10
        assert _count(s, Reference) == len(SAMPLE["references"]) == 5
        defects = s.scalars(select(Box).where(Box.process_id.is_(None))).all()
        assert len(defects) == 7 and {d.fields["group"] for d in defects} == {
            "Surface",
            "Internal",
            "Cracks",
            "Other",
        }
        fm_level = s.scalars(select(Box).where(Box.key == "fm-level")).one()
        assert fm_level.body_md.startswith("Waves at the meniscus")
        assert_revisions_match_rows(s)
