"""Moving tasks in the team-wide ranking over HTTP, including concurrent moves."""

import random
import threading

import pytest
from fastapi.testclient import TestClient

from taskboard.config import Settings
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.web import create_app
from taskboard.web.csrf import CSRF_COOKIE, CSRF_HEADER
from tests.api.conftest import Ids, LoginAs, ranked_keys, ranks
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.helpers import login


def test_drop_before_a_row_moves_the_task_there(
    login_as: LoginAs, sample_database: Database
) -> None:
    client = login_as("admin")
    before = client.get("/api/tasks/T-089").json()
    moved = client.post("/api/tasks/T-089/move", json={"target": "T-117", "where": "before"}).json()
    assert moved["rank"] == 2
    assert ranked_keys(sample_database)[:5] == ["104", "089", "117", "098", "130"]
    # Re-ranking is not an edit: the version (and so anyone's open edit form) is untouched.
    assert moved["version"] == before["version"]
    assert moved["updated_at"] == before["updated_at"]


def test_drop_after_a_row_further_down(login_as: LoginAs, sample_database: Database) -> None:
    client = login_as("admin")
    client.post("/api/tasks/T-104/move", json={"target": "T-126", "where": "after"})
    assert ranked_keys(sample_database) == [
        "117",
        "098",
        "130",
        "089",
        "121",
        "133",
        "126",
        "104",
        "110",
        "075",
        "062",
    ]
    assert ranks(sample_database) == list(range(1, 12))


def test_dropping_on_itself_changes_nothing(login_as: LoginAs, sample_database: Database) -> None:
    before = ranked_keys(sample_database)
    login_as("admin").post("/api/tasks/T-098/move", json={"target": "T-098", "where": "after"})
    assert ranked_keys(sample_database) == before


def test_moving_needs_edit_rights_on_the_moved_task(
    board: TestClient, login_as: LoginAs, ids: Ids
) -> None:
    move = {"target": "T-104", "where": "before"}
    assert board.post("/api/tasks/T-130/move", json=move).status_code == 401
    client = login_as(
        "quality.editor", [(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    assert client.post("/api/tasks/T-130/move", json=move).status_code == 403  # T-130 is R&D
    assert client.post("/api/tasks/T-089/move", json=move).status_code == 200


def test_the_target_must_exist(login_as: LoginAs) -> None:
    client = login_as("admin")
    response = client.post("/api/tasks/T-089/move", json={"target": "T-999", "where": "before"})
    assert response.status_code == 404


def test_concurrent_moves_keep_the_ranking_consistent(
    settings: Settings, sample_database: Database
) -> None:
    """Four clients reorder at the same time; the ranking must stay a permutation of 1..N."""
    keys = ranked_keys(sample_database)
    app = create_app(settings)
    failures: list[str] = []

    def worker(seed: int) -> None:
        client = TestClient(app)  # the app is already started below; no second startup
        client.get("/api/health")
        client.headers[CSRF_HEADER] = client.cookies[CSRF_COOKIE]
        login(client, "admin", TEST_ADMIN_PASSWORD)
        rng = random.Random(seed)
        for _ in range(15):
            task, target = rng.sample(keys, 2)
            where = rng.choice(["before", "after"])
            response = client.post(
                f"/api/tasks/{task}/move", json={"target": target, "where": where}
            )
            if response.status_code != 200:
                failures.append(response.text)

    with TestClient(app):  # runs the startup (migrations, seed) once
        threads = [threading.Thread(target=worker, args=(seed,)) for seed in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    assert failures == []
    assert ranks(sample_database) == list(range(1, len(keys) + 1))
    assert sorted(ranked_keys(sample_database)) == sorted(keys)


@pytest.mark.parametrize("where", ["above", ""])
def test_where_must_be_before_or_after(login_as: LoginAs, where: str) -> None:
    client = login_as("admin")
    response = client.post("/api/tasks/T-089/move", json={"target": "T-104", "where": where})
    assert response.status_code == 422
