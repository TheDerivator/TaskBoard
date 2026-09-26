"""A board with 5,000 extra tasks (milestone M10): the API stays fast and the ranking dense.

Time limits are several times what a laptop needs, so they catch regressions such as a query
per task, not slow machines.
"""

import time

import pytest
from fastapi.testclient import TestClient

from taskboard.db.session import Database
from tests.api.conftest import LoginAs, ranks
from tests.scale import add_tasks

EXTRA = 5000
TOTAL = 11 + EXTRA  # the sample board's tasks plus the generated ones


@pytest.fixture
def admin(sample_database: Database, login_as: LoginAs) -> TestClient:
    with sample_database.session(write=True) as s:
        add_tasks(s, EXTRA)
    return login_as("admin")


def timed(client: TestClient, method: str, url: str, limit: float, **kwargs: object) -> dict:
    start = time.perf_counter()
    response = client.request(method, url, **kwargs)  # type: ignore[arg-type]
    elapsed = time.perf_counter() - start
    assert response.status_code == 200, response.text
    assert elapsed < limit, f"{method} {url} took {elapsed:.2f}s (limit {limit}s)"
    return response.json()


def test_listing_every_task(admin: TestClient) -> None:
    listed = timed(admin, "GET", "/api/tasks", limit=2.0)
    assert listed["total"] == TOTAL
    assert [t["rank"] for t in listed["tasks"]] == list(range(1, TOTAL + 1))


def test_searching(admin: TestClient) -> None:
    found = timed(admin, "GET", "/api/tasks", limit=1.0, params={"q": "grinding"})
    assert 0 < len(found["tasks"]) < TOTAL


def test_moving_the_last_task_to_the_top_keeps_ranks_dense(
    admin: TestClient, sample_database: Database
) -> None:
    listed = admin.get("/api/tasks").json()["tasks"]
    last, first = listed[-1]["key"], listed[0]["key"]
    timed(
        admin,
        "POST",
        f"/api/tasks/{last}/move",
        limit=1.0,
        json={"target": first, "where": "before"},
    )
    assert ranks(sample_database) == list(range(1, TOTAL + 1))
    assert admin.get(f"/api/tasks/{last}").json()["rank"] == 1


def test_a_project_outline_with_thousands_of_placements(admin: TestClient) -> None:
    timed(admin, "GET", "/api/projects/ASQ/outline", limit=1.5)
