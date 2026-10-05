"""Processes (milestone M11): administration, the bootstrap, and who may see them (D-079, D-080)."""

from fastapi.testclient import TestClient

from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Permission, Scope
from tests.api.conftest import Ids, LoginAs
from tests.helpers import login, make_role, make_user, revoke_anonymous_access


def _codes(body: dict) -> list[str]:  # type: ignore[type-arg]
    return [p["code"] for p in body["processes"]]


def test_bootstrap_lists_the_processes_and_the_servers_date(board: TestClient, ids: Ids) -> None:
    body = board.get("/api/bootstrap").json()
    assert body["today"] == "2026-10-03"  # pinned by the test settings
    assert [(p["code"], p["name"]) for p in body["processes"]] == [
        ("CV", "Convertor"),
        ("LM", "Ladle metallurgy"),
        ("CC", "Continuous casting"),
    ]
    assert {(p["section_id"], p["department_id"]) for p in body["processes"]} == {
        (ids.sections["Process"], ids.departments["STL"])
    }


def test_anonymous_visitors_see_the_new_modules_until_an_admin_revokes_it(
    board: TestClient, sample_database: Database
) -> None:
    permissions = board.get("/api/bootstrap").json()["me"]["permissions"]
    assert permissions["change.view"]["everywhere"] and permissions["knowledge.view"]["everywhere"]
    assert not permissions["change.edit"]["everywhere"]
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    body = board.get("/api/bootstrap").json()
    assert body["processes"] == [] and body["departments"] == []


def test_someone_who_may_only_read_process_knowledge_gets_a_working_board(
    board: TestClient, sample_database: Database, ids: Ids
) -> None:
    """No task rights at all: no tasks or projects, but the organization and the processes."""
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
        make_role(s, "map-reader", [Permission.KNOWLEDGE_VIEW])
        make_user(s, "reader", roles=[("map-reader", Scope.section(ids.sections["Process"]))])
    assert login(board, "reader").status_code == 200
    response = board.get("/api/bootstrap")
    assert response.status_code == 200
    body = response.json()
    assert _codes(body) == ["CV", "LM", "CC"]
    assert len(body["people"]) == 6 and len(body["departments"]) == 2
    assert body["projects"] == [] and body["task_total"] == 0


def test_rights_on_another_section_do_not_show_the_processes(
    board: TestClient, sample_database: Database, ids: Ids
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
        make_user(
            s, "quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
        )
    login(board, "quality")
    body = board.get("/api/bootstrap").json()
    assert body["task_total"] > 0 and _codes(body) == []


def test_processes_are_managed_by_organization_administrators(login_as: LoginAs, ids: Ids) -> None:
    admin = login_as("admin")
    created = admin.post(
        "/api/admin/processes",
        json={"code": "hm", "name": "Hot metal", "section_id": ids.sections["Process"]},
    )
    assert created.status_code == 201, created.text
    process = created.json()
    assert process["code"] == "HM" and process["department_id"] == ids.departments["STL"]
    assert [p["code"] for p in admin.get("/api/admin/processes").json()][-1] == "HM"

    updated = admin.patch(
        f"/api/admin/processes/{process['id']}",
        json={"name": "Hot metal desulphurisation", "section_id": ids.sections["Coatings"]},
    ).json()
    assert updated["name"] == "Hot metal desulphurisation"
    assert updated["department_id"] == ids.departments["R&D"]
    # The code is part of change keys and links: it cannot be changed.
    kept = admin.patch(f"/api/admin/processes/{process['id']}", json={"code": "XX"}).json()
    assert kept["code"] == "HM"

    assert admin.delete(f"/api/admin/processes/{process['id']}").status_code == 204
    assert admin.delete(f"/api/admin/processes/{process['id']}").status_code == 404


def test_process_input_is_checked(login_as: LoginAs, ids: Ids) -> None:
    admin = login_as("admin")
    process_section = ids.sections["Process"]
    duplicate = {"code": "cc", "name": "Again", "section_id": process_section}
    assert admin.post("/api/admin/processes", json=duplicate).status_code == 409
    dash = {"code": "C-C", "name": "Dash", "section_id": process_section}
    assert admin.post("/api/admin/processes", json=dash).status_code == 422
    nowhere = {"code": "NW", "name": "Nowhere", "section_id": 999_999}
    assert admin.post("/api/admin/processes", json=nowhere).status_code == 404


def test_a_process_with_changes_cannot_be_deleted(login_as: LoginAs, ids: Ids) -> None:
    admin = login_as("admin")
    response = admin.delete(f"/api/admin/processes/{ids.processes['LM']}")
    assert response.status_code == 409 and "6 process change(s)" in response.json()["message"]


def test_a_section_that_owns_processes_cannot_be_deleted(login_as: LoginAs, ids: Ids) -> None:
    admin = login_as("admin")
    response = admin.delete(f"/api/admin/sections/{ids.sections['Process']}")
    assert response.status_code == 409 and "3 processes" in response.json()["message"]


def test_process_administration_needs_people_manage(board: TestClient, login_as: LoginAs) -> None:
    assert board.get("/api/admin/processes").status_code == 401
    editor = login_as("editor", roles=[(BuiltinRole.EDITOR, Scope.everywhere())])
    assert editor.get("/api/admin/processes").status_code == 403
    assert editor.post("/api/admin/processes", json={}).status_code in {403, 422}
