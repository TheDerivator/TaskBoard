"""Projects API: trees with counts, outlines (DESIGN rule 7), editing projects and sections."""

from fastapi.testclient import TestClient

from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.api.conftest import Ids, LoginAs
from tests.helpers import revoke_anonymous_access


def outline_of(body: dict) -> list[tuple[str, int, list[str]]]:  # type: ignore[type-arg]
    return [
        (s["node"]["number"], s["node"]["count"], [t["key"] for t in s["tasks"]])
        for s in body["sections"]
    ]


def test_projects_with_counts_including_descendants(board: TestClient) -> None:
    projects = {p["key"]: p for p in board.get("/api/projects").json()}
    assert list(projects) == ["ASQ", "P26", "SAF"]
    asq = projects["ASQ"]
    assert asq["count"] == 6  # T-062 is archived
    counts = {n["number"]: n["count"] for n in asq["nodes"]}
    assert counts == {"1": 2, "1.1": 1, "1.2": 1, "2": 3, "2.1": 1, "2.2": 1, "2.2.1": 1, "3": 1}
    with_archived = {
        p["key"]: p for p in board.get("/api/projects", params={"include_archived": True}).json()
    }
    assert with_archived["ASQ"]["count"] == 7


def test_whole_project_outline(board: TestClient, ids: Ids) -> None:
    body = board.get("/api/projects/asq/outline").json()
    assert outline_of(body) == [
        ("1", 2, []),
        ("1.1", 1, ["117"]),
        ("1.2", 1, ["121"]),
        ("2", 3, ["075"]),
        ("2.1", 1, ["104"]),
        ("2.2", 1, []),
        ("2.2.1", 1, ["098"]),
        ("3", 1, ["089"]),
    ]
    assert body["top_level_tasks"] == []
    assert body["breadcrumb"] == [{"node_id": None, "label": "Action plan surface quality"}]
    assert body["open_count"] == 6
    people = ids.people
    assert body["lead_ids"] == [
        people["AC"],
        people["CM"],
        people["DW"],
        people["EJ"],
        people["BP"],
    ]


def test_one_section_unfolds_its_subtree(board: TestClient, ids: Ids) -> None:
    body = board.get("/api/projects/ASQ/outline", params={"node": ids.nodes["ASQ:2.2"]}).json()
    assert outline_of(body) == [("2.2", 1, []), ("2.2.1", 1, ["098"])]
    assert [c["label"] for c in body["breadcrumb"]] == [
        "Action plan surface quality",
        "2 Line 2 defects",
        "2.2 Roll maintenance",
    ]
    assert body["node"]["number"] == "2.2" and body["open_count"] == 1


def test_archived_tasks_only_on_request(board: TestClient, ids: Ids) -> None:
    node = ids.nodes["ASQ:3"]
    hidden = board.get("/api/projects/ASQ/outline", params={"node": node}).json()
    shown = board.get(
        "/api/projects/ASQ/outline", params={"node": node, "include_archived": True}
    ).json()
    assert outline_of(hidden) == [("3", 1, ["089"])]
    assert outline_of(shown) == [("3", 2, ["089", "062"])]
    assert shown["open_count"] == 1  # archived tasks are never "open"


def test_outline_errors(board: TestClient, ids: Ids) -> None:
    assert board.get("/api/projects/NOPE/outline").status_code == 404
    assert (
        board.get("/api/projects/SAF/outline", params={"node": ids.nodes["ASQ:1"]}).status_code
        == 404
    )


def test_counts_only_include_visible_tasks(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    client = login_as("rnd", [(BuiltinRole.VIEWER, Scope.department(ids.departments["R&D"]))])
    projects = {p["key"]: p["count"] for p in client.get("/api/projects").json()}
    assert projects == {"ASQ": 0, "P26": 1, "SAF": 0}


# ---------------------------------------------------------------- editing


def test_only_project_managers_edit_structure(
    board: TestClient, login_as: LoginAs, ids: Ids
) -> None:
    new = {"key": "Q27", "name": "Quality 2027", "color": "#336699"}
    assert board.post("/api/projects", json=new).status_code == 401
    editor = login_as("editor", [(BuiltinRole.EDITOR, Scope.everywhere())])
    assert editor.post("/api/projects", json=new).status_code == 403
    assert editor.post("/api/projects/ASQ/nodes", json={"name": "X"}).status_code == 403


def test_create_update_and_delete_a_project(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    created = client.post(
        "/api/projects", json={"key": "q27", "name": "Quality 2027", "color": "#336699"}
    )
    assert created.status_code == 201
    assert (created.json()["key"], created.json()["position"]) == ("Q27", 3)
    assert (
        client.post(
            "/api/projects", json={"key": "Q27", "name": "Again", "color": "#000000"}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/projects", json={"key": "Q", "name": "x", "color": "#000000"}).status_code
        == 422
    )
    assert (
        client.post("/api/projects", json={"key": "QQ", "name": "x", "color": "red"}).status_code
        == 422
    )
    renamed = client.patch(
        "/api/projects/Q27", json={"name": "Quality 2027 (draft)", "archived": True}
    ).json()
    assert (renamed["name"], renamed["archived"]) == ("Quality 2027 (draft)", True)

    assert client.delete("/api/projects/SAF").status_code == 204
    assert client.get("/api/tasks/T-110").json()["placements"] == []  # the task stays
    assert [p["key"] for p in client.get("/api/projects").json()] == ["ASQ", "P26", "Q27"]


def test_add_rename_and_reorder_sections(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    after_add = client.post("/api/projects/SAF/nodes", json={"name": "Lifting"}).json()
    assert [(n["number"], n["name"]) for n in after_add["nodes"]] == [
        ("1", "Machine guarding"),
        ("1.1", "Coiler"),
        ("2", "Lifting"),
    ]
    lifting = after_add["nodes"][2]["id"]
    child = client.post(
        "/api/projects/SAF/nodes", json={"name": "Cranes", "parent_id": lifting}
    ).json()
    assert [n["number"] for n in child["nodes"]] == ["1", "1.1", "2", "2.1"]
    reordered = client.patch(
        f"/api/projects/SAF/nodes/{lifting}", json={"index": 0, "name": "Lifting gear"}
    ).json()
    assert [(n["number"], n["name"]) for n in reordered["nodes"]] == [
        ("1", "Lifting gear"),
        ("1.1", "Cranes"),
        ("2", "Machine guarding"),
        ("2.1", "Coiler"),
    ]


def test_moving_a_section_under_another_and_back_to_top(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    grinding = ids.nodes["ASQ:2.2.1"]
    inside = client.patch(
        f"/api/projects/ASQ/nodes/{grinding}", json={"parent_id": ids.nodes["ASQ:1"]}
    ).json()
    assert {n["name"]: n["number"] for n in inside["nodes"]}["Grinding"] == "1.3"
    top = client.patch(
        f"/api/projects/ASQ/nodes/{grinding}", json={"parent_id": None, "index": 0}
    ).json()
    numbers = {n["name"]: n["number"] for n in top["nodes"]}
    assert numbers["Grinding"] == "1" and numbers["Measurement & inspection"] == "2"
    assert client.get("/api/tasks/T-098").json()["placements"][0]["number"] == "1"


def test_a_section_cannot_move_into_itself(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    response = client.patch(
        f"/api/projects/ASQ/nodes/{ids.nodes['ASQ:2']}", json={"parent_id": ids.nodes["ASQ:2.2.1"]}
    )
    assert response.status_code == 422
    other_project = client.patch(
        f"/api/projects/ASQ/nodes/{ids.nodes['ASQ:2']}", json={"parent_id": ids.nodes["SAF:1"]}
    )
    assert other_project.status_code == 422


def test_deleting_a_section_moves_its_tasks_up(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    after = client.delete(f"/api/projects/ASQ/nodes/{ids.nodes['ASQ:2.2']}").json()
    assert [n["number"] for n in after["nodes"]] == ["1", "1.1", "1.2", "2", "2.1", "3"]
    placement = client.get("/api/tasks/T-098").json()["placements"][0]
    assert (placement["number"], placement["path"]) == ("2", ["Line 2 defects"])
    top = client.delete(f"/api/projects/ASQ/nodes/{ids.nodes['ASQ:3']}").json()
    assert [n["number"] for n in top["nodes"]] == ["1", "1.1", "1.2", "2", "2.1"]
    assert client.get("/api/tasks/T-089").json()["placements"][0]["number"] is None  # top level


def test_unknown_projects_and_nodes(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    assert client.patch("/api/projects/NOPE", json={"name": "x"}).status_code == 404
    assert client.patch("/api/projects/SAF/nodes/999999", json={"name": "x"}).status_code == 404
    assert client.delete("/api/projects/SAF/nodes/999999").status_code == 404
    wrong_parent = client.post(
        "/api/projects/SAF/nodes", json={"name": "x", "parent_id": ids.nodes["ASQ:1"]}
    )
    assert wrong_parent.status_code == 422
