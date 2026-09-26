"""Task API on the sample board: listing and filters, keys, create, edit, events, delete, access."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from taskboard.db.models import Event, Task, User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.domain.task_keys import ALPHABET
from tests.api.conftest import Ids, LoginAs, ranks
from tests.helpers import revoke_anonymous_access

SAMPLE_ORDER = ["104", "117", "098", "130", "089", "121", "133", "126", "110", "075", "062"]
SHOWN_BY_DEFAULT = ["idea", "started", "done"]


def refs(response_json: dict) -> list[str]:  # type: ignore[type-arg]
    return [t["key"] for t in response_json["tasks"]]


def events(database: Database, key: str) -> list[tuple[str, dict]]:  # type: ignore[type-arg]
    with database.session() as s:
        task_id = s.scalars(select(Task.id).where(Task.key == key)).one()
        return [
            (e.kind.value, e.data)
            for e in s.scalars(select(Event).where(Event.task_id == task_id).order_by(Event.id))
        ]


# ---------------------------------------------------------------- listing and filters


def test_everything_in_team_rank_order(board: TestClient) -> None:
    body = board.get("/api/tasks").json()
    assert refs(body) == SAMPLE_ORDER
    assert [t["rank"] for t in body["tasks"]] == list(range(1, 12))
    assert body["total"] == 11


def test_filters_hide_tasks_but_never_change_ranks(board: TestClient) -> None:
    body = board.get("/api/tasks", params={"statuses": ["started"]}).json()
    assert [(t["key"], t["rank"]) for t in body["tasks"]] == [
        ("104", 1),
        ("117", 2),
        ("130", 4),
        ("089", 5),
    ]
    assert body["total"] == 11


def test_default_lifecycle_filter_hides_archived(board: TestClient) -> None:
    body = board.get("/api/tasks", params={"statuses": SHOWN_BY_DEFAULT}).json()
    assert "062" not in refs(body) and len(body["tasks"]) == 10


def test_search_matches_title_and_description_ignoring_case(board: TestClient) -> None:
    # "roll" is in T-098's title ("work-roll") and T-104's description ("roll changes").
    assert refs(board.get("/api/tasks", params={"q": "ROLL"}).json()) == ["104", "098"]
    assert refs(board.get("/api/tasks", params={"q": "  spc "}).json()) == ["126"]
    assert refs(board.get("/api/tasks", params={"q": "100%"}).json()) == []  # % is literal


def test_search_folds_case_beyond_ascii(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    client.post(
        "/api/tasks",
        json={
            "title": "ÉCRAN de contrôle",
            "lead_id": ids.people["AC"],
            "section_id": ids.sections["Quality"],
        },
    )
    assert [
        t["title"] for t in client.get("/api/tasks", params={"q": "écran"}).json()["tasks"]
    ] == ["ÉCRAN de contrôle"]


def test_organization_filters(board: TestClient, ids: Ids) -> None:
    assert refs(
        board.get("/api/tasks", params={"department_id": ids.departments["R&D"]}).json()
    ) == ["130"]
    quality = refs(board.get("/api/tasks", params={"section_id": ids.sections["Quality"]}).json())
    assert quality == ["104", "117", "089", "075", "062"]


def test_project_and_subtree_filters(board: TestClient, ids: Ids) -> None:
    safety = board.get("/api/tasks", params={"project_id": ids.projects["SAF"]}).json()
    assert refs(safety) == ["110"]
    subtree = board.get("/api/tasks", params={"node_id": ids.nodes["ASQ:2"]}).json()
    assert refs(subtree) == ["104", "098", "075"]  # on 2.1, 2.2.1 and 2 itself


def test_person_filters(board: TestClient, ids: Ids) -> None:
    cm = ids.people["CM"]
    lead = board.get("/api/tasks", params={"person_id": cm, "person_role": "lead"}).json()
    helper = board.get("/api/tasks", params={"person_id": cm, "person_role": "helper"}).json()
    anyrole = board.get("/api/tasks", params={"person_id": cm}).json()
    assert refs(lead) == ["117", "130"]
    assert refs(helper) == ["089", "133"]
    assert refs(anyrole) == ["117", "130", "089", "133"]


def test_invalid_filter_values_are_rejected(board: TestClient) -> None:
    assert board.get("/api/tasks", params={"statuses": ["finished"]}).status_code == 422


# ---------------------------------------------------------------- one task


def test_keys_are_forgiving_and_tasks_have_permalinks(board: TestClient) -> None:
    for key in ("104", "t-104", "T-104", " T-104 "):
        detail = board.get(f"/api/tasks/{key}").json()
        assert (detail["key"], detail["ref"], detail["url"]) == ("104", "T-104", "/t/104")
    assert board.get("/api/tasks/T-999").status_code == 404
    assert board.get("/api/tasks/not-a-key!").status_code == 404


def test_detail_shows_placements_with_numbers_and_paths(board: TestClient, ids: Ids) -> None:
    detail = board.get("/api/tasks/T-098").json()
    assert detail["placements"] == [
        {
            "project_id": ids.projects["ASQ"],
            "node_id": ids.nodes["ASQ:2.2.1"],
            "number": "2.2.1",
            "path": ["Line 2 defects", "Roll maintenance", "Grinding"],
        },
        {
            "project_id": ids.projects["P26"],
            "node_id": ids.nodes["P26:2"],
            "number": "2",
            "path": ["Process"],
        },
    ]
    assert detail["rank"] == 3 and detail["rank_total"] == 11
    assert detail["lead_id"] == ids.people["DW"] and detail["helper_ids"] == [ids.people["BP"]]
    assert detail["permissions"] == {"edit": False, "comment": False, "delete": False}


# ---------------------------------------------------------------- create


def test_anonymous_visitors_must_log_in_to_create(board: TestClient, ids: Ids) -> None:
    body = {"title": "X", "lead_id": ids.people["AC"], "section_id": ids.sections["Quality"]}
    response = board.post("/api/tasks", json=body)
    assert response.status_code == 401
    assert response.json()["error"] == "authentication_required"


def test_section_rights_decide_where_an_editor_may_create(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    client = login_as(
        "stl.editor", [(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))]
    )
    body = {
        "title": "  Calibrate the gauge  ",
        "lead_id": ids.people["FM"],
        "helper_ids": [ids.people["BP"], ids.people["FM"], ids.people["BP"]],
        "section_id": ids.sections["Process"],
        "placements": [{"project_id": ids.projects["P26"], "node_id": ids.nodes["P26:2.2"]}],
    }
    response = client.post("/api/tasks", json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["title"] == "Calibrate the gauge"
    assert len(created["key"]) == 6 and set(created["key"]) <= set(ALPHABET)
    assert created["rank"] == 12  # bottom of the ranking
    assert created["helper_ids"] == [ids.people["BP"]]  # deduplicated, lead removed
    assert created["placements"][0]["number"] == "2.2"
    assert created["permissions"] == {"edit": True, "comment": True, "delete": False}
    assert events(sample_database, created["key"]) == [("created", {})]
    with sample_database.session() as s:
        creator = s.scalars(select(Task.created_by_user_id).where(Task.key == created["key"])).one()
        assert s.get(User, creator).username == "stl.editor"  # type: ignore[union-attr]

    elsewhere = body | {"section_id": ids.sections["Coatings"], "placements": []}
    assert client.post("/api/tasks", json=elsewhere).status_code == 403


def test_create_validates_references(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    base = {"title": "T", "lead_id": ids.people["AC"], "section_id": ids.sections["Quality"]}
    assert client.post("/api/tasks", json=base | {"title": "   "}).status_code == 422
    assert client.post("/api/tasks", json=base | {"lead_id": 999}).status_code == 422
    assert client.post("/api/tasks", json=base | {"section_id": 999}).status_code == 422
    wrong_node = {"project_id": ids.projects["SAF"], "node_id": ids.nodes["ASQ:1"]}
    assert client.post("/api/tasks", json=base | {"placements": [wrong_node]}).status_code == 422
    twice = [{"project_id": ids.projects["SAF"]}, {"project_id": ids.projects["SAF"]}]
    assert client.post("/api/tasks", json=base | {"placements": twice}).status_code == 422


# ---------------------------------------------------------------- edit


def test_editing_records_lifecycle_and_people_events(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    client = login_as("admin")
    before = client.get("/api/tasks/T-133").json()  # lead BP, helpers AC, CM, DW
    change = {
        "version": before["version"],
        "status": "started",
        "helper_ids": [ids.people["AC"], ids.people["EJ"]],
        "title": "Roadmap workshop 2027",
    }
    after = client.patch("/api/tasks/T-133", json=change).json()
    assert after["status"] == "started" and after["title"] == "Roadmap workshop 2027"
    assert after["version"] == before["version"] + 1
    assert set(after["helper_ids"]) == {ids.people["AC"], ids.people["EJ"]}
    assert sorted(events(sample_database, "133"), key=str) == sorted(
        [
            ("status_changed", {"from": "idea", "to": "started"}),
            ("helper_removed", {"person": ids.people["CM"]}),
            ("helper_removed", {"person": ids.people["DW"]}),
            ("helper_added", {"person": ids.people["EJ"]}),
        ],
        key=str,
    )


def test_a_helper_who_becomes_lead_stops_being_a_helper(login_as: LoginAs, ids: Ids) -> None:
    client = login_as("admin")
    task = client.get("/api/tasks/T-104").json()  # lead AC, helper DW
    after = client.patch(
        "/api/tasks/T-104", json={"version": task["version"], "lead_id": ids.people["DW"]}
    ).json()
    assert after["lead_id"] == ids.people["DW"] and after["helper_ids"] == []


def test_stale_versions_are_refused(login_as: LoginAs) -> None:
    client = login_as("admin")
    version = client.get("/api/tasks/T-104").json()["version"]
    assert (
        client.patch("/api/tasks/T-104", json={"version": version, "title": "A"}).status_code == 200
    )
    response = client.patch("/api/tasks/T-104", json={"version": version, "title": "B"})
    assert response.status_code == 409
    assert response.json()["error"] == "stale"


def test_moving_a_task_to_another_section_needs_rights_on_both(login_as: LoginAs, ids: Ids) -> None:
    client = login_as(
        "quality.editor", [(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    task = client.get("/api/tasks/T-104").json()
    to_coatings = {"version": task["version"], "section_id": ids.sections["Coatings"]}
    assert client.patch("/api/tasks/T-104", json=to_coatings).status_code == 403
    assert client.patch("/api/tasks/T-130", json={"version": 1, "title": "x"}).status_code == 403


# ---------------------------------------------------------------- delete


def test_only_administrators_delete_and_ranks_stay_dense(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    client = login_as(
        "stl.editor", [(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))]
    )
    assert client.delete("/api/tasks/T-117").status_code == 403
    client.post("/api/auth/logout")
    admin = login_as("admin")
    assert admin.delete("/api/tasks/T-117").status_code == 204
    assert admin.get("/api/tasks/T-117").status_code == 404
    assert ranks(sample_database) == list(range(1, 11))


# ---------------------------------------------------------------- visibility


def test_restricted_viewers_see_only_their_sections_with_global_ranks(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    client = login_as(
        "coatings.viewer", [(BuiltinRole.VIEWER, Scope.section(ids.sections["Coatings"]))]
    )
    body = client.get("/api/tasks").json()
    assert [(t["key"], t["rank"]) for t in body["tasks"]] == [("130", 4)]
    assert body["total"] == 1
    assert client.get("/api/tasks/T-104").status_code == 404  # invisible = not found
    client.post("/api/auth/logout")
    assert client.get("/api/tasks").status_code == 401


def test_a_pending_password_change_blocks_the_board(
    login_as: LoginAs, sample_database: Database
) -> None:
    client = login_as("admin")
    with sample_database.session(write=True) as s:
        admin = s.scalars(select(User).where(User.username == "admin")).one()
        admin.must_change_password = True
    response = client.get("/api/tasks")
    assert response.status_code == 403
    assert response.json()["error"] == "password_change_required"


def test_an_editor_of_both_sections_moves_a_task_between_them(
    login_as: LoginAs, ids: Ids, sample_database: Database
) -> None:
    client = login_as(
        "stl.editor", [(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))]
    )
    task = client.get("/api/tasks/T-104").json()
    body = {"version": task["version"], "section_id": ids.sections["Process"], "description": "New"}
    after = client.patch("/api/tasks/T-104", json=body).json()
    assert (after["section_id"], after["description"]) == (ids.sections["Process"], "New")
    assert (
        "section_changed",
        {"from": ids.sections["Quality"], "to": ids.sections["Process"]},
    ) in events(sample_database, "104")
