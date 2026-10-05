"""Fixtures for API tests on the sample board: a client, id lookups, and users with given roles."""

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from taskboard.config import Settings
from taskboard.db.models import Department, Person, Process, Project, ProjectNode, Section, Task
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.domain.outline import Outline, TreeNode
from taskboard.web import create_app
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.helpers import login, make_user


@dataclass(frozen=True)
class Ids:
    """Database ids of the sample data, by human-readable name."""

    people: dict[str, int]  # by code, "AC"
    sections: dict[str, int]  # by name, "Quality"
    departments: dict[str, int]  # by code, "STL"
    projects: dict[str, int]  # by key, "ASQ"
    nodes: dict[str, int]  # "ASQ:2.2.1"
    processes: dict[str, int]  # by code, "LM"


@pytest.fixture
def board(settings: Settings, sample_database: Database) -> Iterator[TestClient]:
    """An anonymous client on the sample board."""
    del sample_database  # loaded before the app starts
    yield from start_client(create_app(settings))


@pytest.fixture
def ids(sample_database: Database) -> Ids:
    with sample_database.session() as s:
        nodes: dict[str, int] = {}
        for project in s.scalars(select(Project)):
            rows = list(s.scalars(select(ProjectNode).where(ProjectNode.project_id == project.id)))
            outline = Outline(TreeNode(n.id, n.parent_id, n.position) for n in rows)
            nodes |= {f"{project.key}:{outline.number(n.id)}": n.id for n in rows}
        return Ids(
            people={p.code: p.id for p in s.scalars(select(Person))},
            sections={x.name: x.id for x in s.scalars(select(Section))},
            departments=dict(s.execute(select(Department.code, Department.id)).all()),
            projects={p.key: p.id for p in s.scalars(select(Project))},
            nodes=nodes,
            processes=dict(s.execute(select(Process.code, Process.id)).all()),
        )


type LoginAs = Callable[..., TestClient]


@pytest.fixture
def login_as(board: TestClient, sample_database: Database) -> LoginAs:
    """Log the board client in as `admin`, or as a new user holding the given roles."""

    def _login(username: str, roles: Sequence[tuple[BuiltinRole, Scope]] = ()) -> TestClient:
        if username == "admin":
            response = login(board, "admin", TEST_ADMIN_PASSWORD)
        else:
            with sample_database.new_session(write=True) as s:
                make_user(s, username, roles=roles)
            response = login(board, username)
        assert response.status_code == 200, response.text
        return board

    return _login


def ranked_keys(database: Database) -> list[str]:
    with database.session() as s:
        return list(s.scalars(select(Task.key).order_by(Task.rank)))


def ranks(database: Database) -> list[int]:
    with database.session() as s:
        return list(s.scalars(select(Task.rank).order_by(Task.rank)))
