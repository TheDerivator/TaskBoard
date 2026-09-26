"""Administration API: accounts, passwords, rights, roles, organization, audit, lockout guard."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from taskboard.config import Settings
from taskboard.db.models import Role, User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.web import create_app
from tests.api.conftest import Ids, LoginAs
from tests.conftest import start_client
from tests.helpers import login


@pytest.fixture
def admin(login_as: LoginAs) -> TestClient:
    return login_as("admin")


@pytest.fixture
def second_client(settings: Settings, sample_database: Database) -> Iterator[TestClient]:
    """Another browser, for checking what a different account sees."""
    del sample_database
    yield from start_client(create_app(settings))


def role_id(database: Database, key: str) -> int:
    with database.session() as s:
        return s.scalars(select(Role.id).where(Role.key == key)).one()


def user_id(database: Database, username: str) -> int:
    with database.session() as s:
        return s.scalars(select(User.id).where(User.username == username)).one()


# ---------------------------------------------------------------- access to the admin API


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/admin/users"),
        ("GET", "/api/admin/roles"),
        ("GET", "/api/admin/audit"),
        ("GET", "/api/admin/people"),
    ],
)
def test_only_administrators_reach_the_admin_api(
    board: TestClient, login_as: LoginAs, method: str, path: str
) -> None:
    assert board.request(method, path).status_code == 401
    editor = login_as("editor", [(BuiltinRole.EDITOR, Scope.everywhere())])
    assert editor.request(method, path).status_code == 403


def test_people_managers_manage_the_organization_but_not_users(
    admin: TestClient, second_client: TestClient
) -> None:
    """A custom role with only `people.manage`, set up through the admin API itself."""
    role = admin.post(
        "/api/admin/roles", json={"key": "hr", "name": "HR", "permissions": ["people.manage"]}
    ).json()
    admin.post(
        "/api/admin/users",
        json={
            "username": "hr.person",
            "display_name": "HR",
            "password": "people person pw",
            "assignments": [{"role_id": role["id"]}],
        },
    )
    login(second_client, "hr.person", "people person pw")
    assert second_client.get("/api/admin/people").json()["error"] == "password_change_required"
    new_password = {"current_password": "people person pw", "new_password": "my own password"}
    assert second_client.post("/api/auth/password", json=new_password).status_code == 204
    assert second_client.get("/api/admin/people").status_code == 200
    assert second_client.get("/api/admin/users").status_code == 403


# ---------------------------------------------------------------- accounts


def test_create_a_local_account_with_a_generated_password(
    admin: TestClient, second_client: TestClient, sample_database: Database
) -> None:
    body = {
        "username": "Nina.Vos",
        "display_name": "Nina Vos",
        "email": "Nina.Vos@example.com",
        "assignments": [
            {"role_id": role_id(sample_database, "editor"), "scope": "department", "scope_id": 1}
        ],
    }
    response = admin.post("/api/admin/users", json=body)
    assert response.status_code == 201, response.text
    created = response.json()
    user = created["user"]
    assert (user["username"], user["email"], user["status"]) == (
        "nina.vos",
        "nina.vos@example.com",
        "active",
    )
    assert user["must_change_password"] is True and user["has_password"] is True
    assert [(a["role_name"], a["scope_label"]) for a in user["assignments"]] == [("Editor", "STL")]
    password = created["generated_password"]
    assert password and len(password) >= 16

    me = login(second_client, "nina.vos", password).json()
    assert me["must_change_password"] is True
    assert second_client.get("/api/tasks").json()["error"] == "password_change_required"


def test_pre_provision_an_sso_account(admin: TestClient, second_client: TestClient) -> None:
    body = {
        "username": "jan.peeters",
        "display_name": "Jan Peeters",
        "email": "jan@example.com",
        "sso_only": True,
    }
    created = admin.post("/api/admin/users", json=body).json()
    assert created["generated_password"] is None
    assert created["user"]["status"] == "pending" and created["user"]["has_password"] is False
    assert login(second_client, "jan.peeters", "anything at all").status_code == 401


def test_usernames_emails_and_people_are_unique(admin: TestClient, ids: Ids) -> None:
    assert (
        admin.post("/api/admin/users", json={"username": "ADMIN", "display_name": "x"}).status_code
        == 409
    )
    admin.post(
        "/api/admin/users",
        json={"username": "one", "display_name": "One", "email": "same@example.com"},
    )
    clash = admin.post(
        "/api/admin/users",
        json={"username": "two", "display_name": "Two", "email": "SAME@example.com"},
    )
    assert clash.status_code == 409
    anna = ids.people["AC"]  # already linked to the sample account anna.claes
    taken = admin.post(
        "/api/admin/users", json={"username": "three", "display_name": "T", "person_id": anna}
    )
    assert taken.status_code == 409
    assert (
        admin.post(
            "/api/admin/users", json={"username": "x", "display_name": "too short"}
        ).status_code
        == 422
    )


def test_suspension_logs_the_account_out_at_once(
    admin: TestClient, second_client: TestClient, sample_database: Database
) -> None:
    created = admin.post(
        "/api/admin/users",
        json={"username": "tom", "display_name": "Tom", "password": "a strong password"},
    ).json()
    tom = created["user"]["id"]
    login(second_client, "tom", "a strong password")
    assert second_client.get("/api/auth/me").json()["username"] == "tom"

    assert (
        admin.patch(f"/api/admin/users/{tom}", json={"status": "suspended"}).json()["status"]
        == "suspended"
    )
    assert second_client.get("/api/auth/me").json()["is_anonymous"] is True
    assert login(second_client, "tom", "a strong password").status_code == 401

    admin.patch(f"/api/admin/users/{tom}", json={"status": "active"})
    assert login(second_client, "tom", "a strong password").status_code == 200


def test_edit_account_details_and_person_link(
    admin: TestClient, ids: Ids, sample_database: Database
) -> None:
    uid = user_id(sample_database, "anna.claes")
    changed = admin.patch(
        f"/api/admin/users/{uid}",
        json={"display_name": "Anna C.", "email": "anna@example.com", "person_id": None},
    ).json()
    assert (changed["display_name"], changed["email"], changed["person_id"]) == (
        "Anna C.",
        "anna@example.com",
        None,
    )
    relinked = admin.patch(f"/api/admin/users/{uid}", json={"person_id": ids.people["AC"]}).json()
    assert relinked["person_id"] == ids.people["AC"]
    assert admin.patch(f"/api/admin/users/{uid}", json={"email": "not an email"}).status_code == 422


def test_guards_against_locking_everyone_out(admin: TestClient, sample_database: Database) -> None:
    me = user_id(sample_database, "admin")
    anonymous = user_id(sample_database, "anonymous")
    assert admin.patch(f"/api/admin/users/{me}", json={"status": "suspended"}).status_code == 422
    assert (
        admin.patch(f"/api/admin/users/{anonymous}", json={"status": "suspended"}).status_code
        == 422
    )
    own_admin_role = admin.get("/api/admin/users").json()
    assignment = next(u for u in own_admin_role if u["username"] == "admin")["assignments"][0]["id"]
    refused = admin.delete(f"/api/admin/users/{me}/assignments/{assignment}")
    assert (
        refused.status_code == 422
        and "at least one active administrator" in refused.json()["message"]
    )

    # With a second administrator it is allowed.
    other = admin.post(
        "/api/admin/users",
        json={
            "username": "second.admin",
            "display_name": "Second",
            "assignments": [{"role_id": role_id(sample_database, "admin")}],
        },
    ).json()["user"]["id"]
    assert admin.delete(f"/api/admin/users/{me}/assignments/{assignment}").status_code == 200
    assert other


def test_password_reset(admin: TestClient, second_client: TestClient) -> None:
    created = admin.post(
        "/api/admin/users",
        json={"username": "kim", "display_name": "Kim", "password": "first password!"},
    ).json()
    kim = created["user"]["id"]
    login(second_client, "kim", "first password!")
    reset = admin.post(f"/api/admin/users/{kim}/password", json={}).json()
    new_password = reset["generated_password"]
    assert new_password
    assert second_client.get("/api/auth/me").json()["is_anonymous"] is True  # logged out everywhere
    assert login(second_client, "kim", "first password!").status_code == 401
    assert login(second_client, "kim", new_password).json()["must_change_password"] is True
    assert (
        admin.post(f"/api/admin/users/{kim}/password", json={"password": "short"}).status_code
        == 422
    )
    chosen = admin.post(
        f"/api/admin/users/{kim}/password", json={"password": "chosen by admin"}
    ).json()
    assert chosen["generated_password"] is None


# ---------------------------------------------------------------- access rights


def test_revoking_anonymous_access_makes_the_board_login_only(
    admin: TestClient, second_client: TestClient, sample_database: Database
) -> None:
    anonymous = next(u for u in admin.get("/api/admin/users").json() if u["kind"] == "anonymous")
    assert [a["role_name"] for a in anonymous["assignments"]] == ["Viewer"]
    assert second_client.get("/api/tasks").status_code == 200
    admin.delete(
        f"/api/admin/users/{anonymous['id']}/assignments/{anonymous['assignments'][0]['id']}"
    )
    assert second_client.get("/api/tasks").status_code == 401
    # Give visitors view rights on one section only.
    admin.post(
        f"/api/admin/users/{anonymous['id']}/assignments",
        json={"role_id": role_id(sample_database, "viewer"), "scope": "section", "scope_id": 4},
    )
    assert [t["key"] for t in second_client.get("/api/tasks").json()["tasks"]] == ["130"]


def test_assignment_validation(admin: TestClient, sample_database: Database) -> None:
    uid = user_id(sample_database, "anna.claes")
    editor = role_id(sample_database, "editor")
    assert (
        admin.post(
            f"/api/admin/users/{uid}/assignments", json={"role_id": editor, "scope": "section"}
        ).status_code
        == 422
    )
    assert (
        admin.post(
            f"/api/admin/users/{uid}/assignments",
            json={"role_id": editor, "scope": "section", "scope_id": 999},
        ).status_code
        == 422
    )
    assert (
        admin.post(f"/api/admin/users/{uid}/assignments", json={"role_id": 999}).status_code == 422
    )
    # Anna already has Editor on STL (department 1) in the sample.
    assert (
        admin.post(
            f"/api/admin/users/{uid}/assignments",
            json={"role_id": editor, "scope": "department", "scope_id": 1},
        ).status_code
        == 409
    )
    added = admin.post(
        f"/api/admin/users/{uid}/assignments",
        json={"role_id": editor, "scope": "section", "scope_id": 4},
    )
    assert added.status_code == 201
    assert [a["scope_label"] for a in added.json()["assignments"]] == ["STL", "R&D · Coatings"]


def test_custom_roles(admin: TestClient, login_as: LoginAs, sample_database: Database) -> None:
    builtin = role_id(sample_database, "viewer")
    assert admin.patch(f"/api/admin/roles/{builtin}", json={"name": "Watcher"}).status_code == 422
    assert admin.delete(f"/api/admin/roles/{builtin}").status_code == 422

    created = admin.post(
        "/api/admin/roles",
        json={"key": "archivist", "name": "Archivist", "permissions": ["task.view", "task.delete"]},
    )
    assert created.status_code == 201
    role = created.json()
    assert role["permissions"] == ["task.delete", "task.view"] and role["is_builtin"] is False
    assert (
        admin.post("/api/admin/roles", json={"key": "archivist", "name": "Again"}).status_code
        == 409
    )

    archivist = admin.post(
        "/api/admin/users",
        json={
            "username": "arch",
            "display_name": "Arch",
            "password": "archive all the things",
            "assignments": [{"role_id": role["id"], "scope": "section", "scope_id": 1}],
        },
    ).json()
    assert archivist["user"]["assignments"][0]["role_name"] == "Archivist"
    assert admin.delete(f"/api/admin/roles/{role['id']}").status_code == 409  # still assigned

    renamed = admin.patch(
        f"/api/admin/roles/{role['id']}",
        json={"name": "Records keeper", "permissions": ["task.view"]},
    ).json()
    assert renamed["name"] == "Records keeper" and renamed["permissions"] == ["task.view"]
    permissions = admin.get("/api/admin/permissions").json()
    assert {p["value"] for p in permissions} >= {"task.view", "users.manage"}
    assert next(p for p in permissions if p["value"] == "users.manage")["scoped"] is False


# ---------------------------------------------------------------- organization


def test_departments_and_sections(admin: TestClient, ids: Ids) -> None:
    department = admin.post(
        "/api/admin/departments", json={"code": "ops", "name": "Operations"}
    ).json()
    assert department["code"] == "OPS" and department["sections"] == []
    assert (
        admin.post("/api/admin/departments", json={"code": "OPS", "name": "Again"}).status_code
        == 409
    )
    with_section = admin.post(
        "/api/admin/sections", json={"department_id": department["id"], "name": "Logistics"}
    ).json()
    assert [s["name"] for s in with_section["sections"]] == ["Logistics"]
    assert (
        admin.post(
            "/api/admin/sections", json={"department_id": department["id"], "name": "Logistics"}
        ).status_code
        == 409
    )
    assert (
        admin.delete(f"/api/admin/departments/{department['id']}").status_code == 409
    )  # has a section
    section = with_section["sections"][0]["id"]
    assert (
        admin.patch(f"/api/admin/sections/{section}", json={"name": "Shipping"}).json()["sections"][
            0
        ]["name"]
        == "Shipping"
    )
    assert admin.delete(f"/api/admin/sections/{section}").status_code == 200
    assert admin.delete(f"/api/admin/departments/{department['id']}").status_code == 204

    used = admin.delete(f"/api/admin/sections/{ids.sections['Quality']}")
    assert used.status_code == 409 and "tasks" in used.json()["message"]


def test_people(admin: TestClient, ids: Ids) -> None:
    people = admin.get("/api/admin/people").json()
    anna = next(p for p in people if p["code"] == "AC")
    assert anna["user_id"] is not None and anna["department_id"] == ids.departments["STL"]
    body = {
        "code": "gv",
        "name": "Greet Vos",
        "color": "#1F7A6E",
        "email": "Greet@example.com",
        "section_id": ids.sections["Process"],
    }
    created = admin.post("/api/admin/people", json=body).json()
    assert (created["code"], created["email"], created["active"]) == (
        "GV",
        "greet@example.com",
        True,
    )
    assert admin.post("/api/admin/people", json=body).status_code == 409
    assert (
        admin.patch(f"/api/admin/people/{created['id']}", json={"active": False}).json()["active"]
        is False
    )
    leads = admin.patch(f"/api/admin/people/{anna['id']}", json={"active": False})
    assert leads.status_code == 422 and "still leads" in leads.json()["message"]
    assert (
        admin.patch(f"/api/admin/people/{created['id']}", json={"color": "red"}).status_code == 422
    )


# ---------------------------------------------------------------- audit


def test_everything_ends_up_in_the_audit_log(admin: TestClient) -> None:
    admin.post(
        "/api/admin/users",
        json={"username": "audited", "display_name": "Audited", "password": "a strong password"},
    )
    admin.post("/api/admin/departments", json={"code": "AUD", "name": "Audit"})
    entries = admin.get("/api/admin/audit", params={"limit": 5}).json()
    assert [e["action"] for e in entries[:3]] == [
        "department.created",
        "user.created",
        "auth.login",
    ]
    assert entries[0]["actor"] == "Administrator"
    older = admin.get("/api/admin/audit", params={"before_id": entries[0]["id"], "limit": 1}).json()
    assert older[0]["id"] == entries[1]["id"]
