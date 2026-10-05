"""The database itself guards the core invariants (so no code path can break them)."""

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Box,
    BoxLink,
    Change,
    ChangePeriod,
    Person,
    Placement,
    Post,
    Process,
    Project,
    ProjectNode,
    Release,
    Role,
    RoleAssignment,
    Section,
    Task,
    User,
)
from taskboard.db.session import Database
from taskboard.domain.access import Scope
from taskboard.domain.changes import PeriodKind


def _first[T](session: Session, model: type[T]) -> T:
    return session.scalars(select(model)).first()  # type: ignore[return-value]


@pytest.fixture
def s(sample_database: Database) -> Iterator[Session]:
    with sample_database.new_session(write=True) as session:
        yield session


def _task(s: Session, key: str) -> Task:
    return s.scalars(select(Task).where(Task.key == key)).one()


def _project(s: Session, key: str) -> Project:
    return s.scalars(select(Project).where(Project.key == key)).one()


def test_a_task_sits_at_most_once_in_a_project(s: Session) -> None:
    # T-104 is already placed in ASQ.
    s.add(Placement(task_id=_task(s, "104").id, project_id=_project(s, "ASQ").id, node_id=None))
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_placement_node_must_belong_to_the_same_project(s: Session) -> None:
    saf_node = s.scalars(
        select(ProjectNode).where(ProjectNode.project_id == _project(s, "SAF").id)
    ).first()
    assert saf_node
    # T-130 is not in ASQ yet, but the node belongs to SAF.
    s.add(
        Placement(task_id=_task(s, "130").id, project_id=_project(s, "ASQ").id, node_id=saf_node.id)
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_node_parent_must_belong_to_the_same_project(s: Session) -> None:
    asq_node = s.scalars(
        select(ProjectNode).where(ProjectNode.project_id == _project(s, "ASQ").id)
    ).first()
    assert asq_node
    s.add(ProjectNode(project_id=_project(s, "SAF").id, parent_id=asq_node.id, name="Wrong"))
    with pytest.raises(IntegrityError):
        s.flush()


def test_task_keys_are_unique(s: Session) -> None:
    template = _task(s, "104")
    s.add(
        Task(
            key="104",
            title="Duplicate",
            rank=99,
            lead_person_id=template.lead_person_id,
            section_id=template.section_id,
        )
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_foreign_keys_are_enforced(s: Session) -> None:
    s.add(Person(code="ZZ", name="Nobody", color="#000000", section_id=987654))
    with pytest.raises(IntegrityError):
        s.flush()


def test_an_assignment_has_at_most_one_scope(s: Session) -> None:
    section = _first(s, Section)
    user = s.scalars(select(User).where(User.username == "anna.claes")).one()
    assignment = RoleAssignment(
        user_id=user.id,
        role_id=_first(s, Role).id,
        department_id=section.department_id,
        section_id=section.id,
        scope_key="broken",
    )
    s.add(assignment)
    with pytest.raises(IntegrityError):
        s.flush()


def test_the_same_role_twice_at_the_same_scope_is_rejected(s: Session) -> None:
    user = s.scalars(select(User).where(User.username == "anna.claes")).one()
    role = user.assignments[0].role
    duplicate = RoleAssignment(role=role)
    duplicate.scope = user.assignments[0].scope
    user.assignments.append(duplicate)
    with pytest.raises(IntegrityError):
        s.flush()


def test_many_users_without_email_but_no_duplicate_emails(s: Session) -> None:
    """Filtered unique index: NULLs don't collide (MS SQL's plain UNIQUE would allow only one)."""
    s.add_all([User(username="x1", display_name="X1"), User(username="x2", display_name="X2")])
    s.flush()
    s.add_all(
        [
            User(username="y1", display_name="Y1", email="same@example.com"),
            User(username="y2", display_name="Y2", email="same@example.com"),
        ]
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_scope_round_trips_through_an_assignment() -> None:
    assignment = RoleAssignment()
    for scope in (Scope.everywhere(), Scope.department(3), Scope.section(7)):
        assignment.scope = scope
        assert assignment.scope == scope
        assert assignment.scope_key == scope.key


def test_emails_and_usernames_are_stored_normalized(s: Session) -> None:
    user = User(username="  Mixed.Case ", display_name="M", email="  Mixed@Example.COM ")
    person = Person(code="MC", name="M", color="#000000", email="Mixed@Example.COM", section_id=1)
    assert (user.username, user.email, person.email) == (
        "mixed.case",
        "mixed@example.com",
        "mixed@example.com",
    )
    assert User(username="u", display_name="U", email="   ").email is None


def test_a_period_is_posted_in_its_own_changes_conversation(s: Session) -> None:
    """change_periods(post_id, change_id) → posts(id, change_id): no period on another's post."""
    lm07, lm08 = (
        s.scalars(select(Change).where(Change.key == k)).one() for k in ("LM-07", "LM-08")
    )
    post = s.scalars(select(Post).where(Post.change_id == lm07.id)).first()
    assert post is not None
    s.add(
        ChangePeriod(
            post_id=post.id,
            change_id=lm08.id,
            kind=PeriodKind.TEST,
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 2),
            label="Test",
            scope_tags=[],
        )
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_post_belongs_to_a_task_or_a_change_never_both(s: Session) -> None:
    change = s.scalars(select(Change)).first()
    assert change is not None
    s.add(Post(task_id=_task(s, "104").id, change_id=change.id, author_user_id=1, body_md="x"))
    with pytest.raises(IntegrityError):
        s.flush()


def _box(s: Session, key: str) -> Box:
    return s.scalars(select(Box).where(Box.key == key)).one()


def test_a_process_map_has_one_root(s: Session) -> None:
    root = _box(s, "cc")
    s.add(Box(key="second-root", process_id=root.process_id, kind_id=root.kind_id, name="Again"))
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_parent_is_in_the_same_process(s: Session) -> None:
    lm = s.scalars(select(Process).where(Process.code == "LM")).one()
    mould = _box(s, "mould")
    s.add(
        Box(key="stray", process_id=lm.id, parent_id=mould.id, kind_id=mould.kind_id, name="Stray")
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_box_is_in_a_process_or_in_a_section_never_both(s: Session) -> None:
    root = _box(s, "cc")
    s.add(
        Box(
            key="both",
            process_id=root.process_id,
            section_id=_task(s, "104").section_id,
            parent_id=root.id,
            kind_id=root.kind_id,
            name="Both",
        )
    )
    with pytest.raises(IntegrityError):
        s.flush()


def test_a_box_does_not_link_to_itself(s: Session) -> None:
    box = _box(s, "fm-level")
    link_type = s.scalars(select(BoxLink.type_id)).first()
    s.add(BoxLink(from_box_id=box.id, to_box_id=box.id, type_id=link_type, note_md=""))
    with pytest.raises(IntegrityError):
        s.flush()


def test_two_releases_of_a_process_never_share_a_number(s: Session) -> None:
    cc = s.scalars(select(Process).where(Process.code == "CC")).one()
    s.add(Release(process_id=cc.id, number=3, note="At the same moment"))
    with pytest.raises(IntegrityError):
        s.flush()
