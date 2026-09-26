"""Placing tasks in projects: one place per project, nodes of that project, events."""

from fastapi.testclient import TestClient

from taskboard.db.session import Database
from tests.api.conftest import Ids, LoginAs
from tests.api.test_tasks import events


def test_add_move_and_remove_a_placement(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    client = login_as("admin")
    p26, saf = ids.projects["P26"], ids.projects["SAF"]
    added = client.post(
        "/api/tasks/T-104/placements", json={"project_id": p26, "node_id": ids.nodes["P26:1.1"]}
    )
    assert added.status_code == 201
    assert [(p["project_id"], p["number"]) for p in added.json()["placements"]] == [
        (ids.projects["ASQ"], "2.1"),
        (p26, "1.1"),
    ]
    moved = client.put(f"/api/tasks/T-104/placements/{p26}", json={"node_id": None}).json()
    assert [(p["project_id"], p["number"]) for p in moved["placements"]][1] == (p26, None)
    removed = client.delete(f"/api/tasks/T-104/placements/{p26}").json()
    assert [p["project_id"] for p in removed["placements"]] == [ids.projects["ASQ"]]
    assert client.delete(f"/api/tasks/T-104/placements/{saf}").status_code == 404
    assert [kind for kind, _ in events(sample_database, "104")] == [
        "status_changed",  # from the sample data
        "placement_added",
        "placement_moved",
        "placement_removed",
    ]


def test_a_task_sits_once_per_project(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    response = client.post("/api/tasks/T-104/placements", json={"project_id": ids.projects["ASQ"]})
    assert response.status_code == 409
    assert "move it there instead" in response.json()["message"]


def test_the_node_must_belong_to_the_project(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    body = {"project_id": ids.projects["SAF"], "node_id": ids.nodes["ASQ:1"]}
    assert client.post("/api/tasks/T-104/placements", json=body).status_code == 422
    assert client.post("/api/tasks/T-104/placements", json={"project_id": 999}).status_code == 404


def test_placing_needs_edit_rights(board: TestClient, ids: Ids) -> None:
    response = board.post("/api/tasks/T-104/placements", json={"project_id": ids.projects["SAF"]})
    assert response.status_code == 401


def test_placement_changes_bump_the_version(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    version = client.get("/api/tasks/T-104").json()["version"]
    after = client.post(
        "/api/tasks/T-104/placements", json={"project_id": ids.projects["SAF"]}
    ).json()
    assert after["version"] == version + 1
