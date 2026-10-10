"""API tokens for AI agents (D-097): acting as the owner, scopes, never administration, refusals,
revoking, expiry, "via" marks on what a token wrote, administrators' view, the agent guide."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from taskboard.config import Settings
from taskboard.db.base import utcnow
from taskboard.db.models import ApiToken, User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.services.tokens import MAX_LIVE_TOKENS
from taskboard.web import create_app
from tests.api.conftest import Ids, LoginAs


@pytest.fixture
def agent(settings: Settings, sample_database: Database) -> Iterator[TestClient]:
    """A client like an AI agent's: no cookies, no CSRF header, only what the test sends."""
    del sample_database
    with TestClient(create_app(settings)) as client:
        yield client


def _token(client: TestClient, name: str = "Claude Code", **body: Any) -> dict[str, Any]:
    response = client.post("/api/auth/tokens", json={"name": name, **body})
    assert response.status_code == 201, response.text
    return response.json()


def _user_id(database: Database, username: str) -> int:
    with database.session() as s:
        return s.scalars(select(User.id).where(User.username == username)).one()


def _as(agent: TestClient, secret: str) -> TestClient:
    agent.headers["Authorization"] = f"Bearer {secret}"
    return agent


@pytest.fixture
def editor(login_as: LoginAs, ids: Ids) -> TestClient:
    """An editor of STL (its tasks, changes, map and defects), logged in on the board."""
    return login_as("stl", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))])


def test_a_token_acts_as_its_owner_and_marks_what_it_writes(
    editor: TestClient, agent: TestClient, sample_database: Database
) -> None:
    created = _token(editor, scope="write")
    assert created["secret"].startswith("tb_") and created["token"]["scope"] == "write"
    assert created["secret"].startswith(created["token"]["prefix"])
    _as(agent, created["secret"])

    me = agent.get("/api/auth/me").json()
    assert me["username"] == "stl"
    assert me["api_token"] == {"name": "Claude Code", "scope": "write"}
    assert editor.get("/api/auth/me").json()["api_token"] is None  # the browser has none

    # Writes need no CSRF header: the token alone decides.
    post = agent.post("/api/tasks/T-104/posts", json={"body_md": "Summary by the agent."})
    assert post.status_code == 201, post.text
    assert post.json()["author"]["via"] == "Claude Code"
    task = agent.get("/api/tasks/T-104").json()
    assert agent.patch(
        "/api/tasks/T-104", json={"version": task["version"], "status": "done"}
    ).is_success

    items = editor.get("/api/tasks/T-104/conversation").json()["items"]
    stl = _user_id(sample_database, "stl")
    mine = [i for i in items if (i.get("author") or i.get("actor") or {}).get("user_id") == stl]
    assert {i["type"] for i in mine} == {"post", "event"}
    assert all((i.get("author") or i.get("actor"))["via"] == "Claude Code" for i in mine)

    # The owner's own posts in the browser carry no mark.
    by_hand = editor.post("/api/tasks/T-104/posts", json={"body_md": "By hand."}).json()
    assert by_hand["author"]["via"] is None


def test_edited_posts_and_their_history_keep_the_marks(
    editor: TestClient, agent: TestClient
) -> None:
    _as(agent, _token(editor, scope="write")["secret"])
    post = editor.post("/api/tasks/T-104/posts", json={"body_md": "First, by hand."}).json()
    edited = agent.patch(
        f"/api/posts/{post['id']}", json={"body_md": "Tidied by the agent.", "is_update": False}
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["author"]["via"] is None
    assert edited.json()["edited_by"]["via"] == "Claude Code"
    history = editor.get(f"/api/posts/{post['id']}/history").json()
    assert [v["written_by"]["via"] for v in history] == [None, "Claude Code"]


def test_knowledge_revisions_show_the_token(editor: TestClient, agent: TestClient) -> None:
    _as(agent, _token(editor, name="Map bot", scope="write")["secret"])
    assert agent.post("/api/boxes/fm-level/reviewed").is_success
    latest = editor.get("/api/boxes/fm-level/history").json()[0]
    assert latest["author"]["display_name"] == "Stl" and latest["author"]["via"] == "Map bot"


def test_a_read_token_reads_but_never_writes(editor: TestClient, agent: TestClient) -> None:
    created = _token(editor)  # read is the default
    assert created["token"]["scope"] == "read"
    _as(agent, created["secret"])
    assert agent.get("/api/tasks/T-104").status_code == 200
    me = agent.get("/api/auth/me").json()
    assert me["permissions"]["task.view"]["everywhere"] is True  # the anonymous floor
    assert me["permissions"]["task.edit"] == {"everywhere": False, "section_ids": []}
    response = agent.post("/api/tasks/T-104/posts", json={"body_md": "Hi"})
    assert response.status_code == 403 and response.json()["error"] == "permission_denied"


def test_administration_is_never_possible_through_a_token(
    login_as: LoginAs, agent: TestClient
) -> None:
    admin = login_as("admin")
    _as(agent, _token(admin, scope="write")["secret"])
    me = agent.get("/api/auth/me").json()
    assert me["permissions"]["users.manage"]["everywhere"] is False
    assert me["permissions"]["people.manage"]["everywhere"] is False
    assert me["permissions"]["task.delete"]["everywhere"] is True  # the rest of the owner's rights
    for path in (
        "/api/admin/users",
        "/api/admin/roles",
        "/api/admin/audit",
        "/api/admin/people",
        "/api/admin/backups",
    ):
        assert agent.get(path).status_code == 403, path
    assert agent.post("/api/admin/departments", json={"code": "X", "name": "X"}).status_code == 403


def test_a_wrong_token_is_refused_instead_of_reading_as_a_visitor(agent: TestClient) -> None:
    assert agent.get("/api/tasks").status_code == 200  # visitors may read the sample board
    for header in ("Bearer tb_nonsense", "Bearer ", "bearer tb_nonsense"):
        agent.headers["Authorization"] = header
        response = agent.get("/api/tasks")
        assert response.status_code == 401, header
        assert response.json()["error"] == "authentication_required"
        assert "token" in response.json()["message"]


def test_a_bearer_header_cannot_borrow_the_browser_session(editor: TestClient) -> None:
    """Writes with a Bearer header skip the CSRF check, so such a request must never be judged
    by its cookies: a made-up token gets 401, not the signed-in user's rights."""
    del editor.headers["X-CSRF-Token"]
    assert editor.post("/api/tasks/T-104/posts", json={"body_md": "x"}).status_code == 403  # CSRF
    response = editor.post(
        "/api/tasks/T-104/posts",
        json={"body_md": "x"},
        headers={"Authorization": "Bearer tb_made_up"},
    )
    assert response.status_code == 401


def test_a_token_wins_over_the_browser_session(
    editor: TestClient, login_as: LoginAs, ids: Ids
) -> None:
    del ids
    secret = _token(editor)["secret"]
    admin = login_as("admin")  # the same client, now with the admin's session cookie
    me = admin.get("/api/auth/me", headers={"Authorization": f"Bearer {secret}"}).json()
    assert me["username"] == "stl" and me["api_token"]["scope"] == "read"


def test_revoking_expiry_and_suspension_end_a_token_at_once(
    editor: TestClient, agent: TestClient, sample_database: Database
) -> None:
    first, second, third = (_token(editor, name=n) for n in ("one", "two", "three"))
    _as(agent, first["secret"])
    assert agent.get("/api/auth/me").status_code == 200
    assert editor.delete(f"/api/auth/tokens/{first['token']['id']}").status_code == 204
    assert agent.get("/api/auth/me").status_code == 401
    assert editor.delete(f"/api/auth/tokens/{first['token']['id']}").status_code == 404  # done

    _as(agent, second["secret"])
    with sample_database.session(write=True) as s:
        s.execute(
            update(ApiToken)
            .where(ApiToken.id == second["token"]["id"])
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )
    assert agent.get("/api/auth/me").status_code == 401
    listed = {t["name"]: t for t in editor.get("/api/auth/tokens").json()}
    assert set(listed) == {"two", "three"} and listed["two"]["expired"] is True

    _as(agent, third["secret"])
    assert agent.get("/api/auth/me").status_code == 200
    with sample_database.session(write=True) as s:
        s.execute(update(User).where(User.username == "stl").values(status=UserStatus.SUSPENDED))
    assert agent.get("/api/auth/me").status_code == 401


def test_tokens_are_managed_on_the_board_not_through_a_token(
    editor: TestClient, agent: TestClient
) -> None:
    created = _token(editor, scope="write")
    _as(agent, created["secret"])
    assert agent.get("/api/auth/tokens").status_code == 403
    assert (
        agent.post("/api/auth/tokens", json={"name": "more", "scope": "write"}).status_code == 403
    )
    assert agent.delete(f"/api/auth/tokens/{created['token']['id']}").status_code == 403
    response = agent.post(
        "/api/auth/password", json={"current_password": "x", "new_password": "y" * 20}
    )
    assert response.status_code == 403


def test_visitors_cannot_have_tokens(board: TestClient) -> None:
    assert board.get("/api/auth/tokens").status_code == 401
    assert board.post("/api/auth/tokens", json={"name": "x"}).status_code == 401


def test_the_secret_is_shown_once_and_only_its_hash_is_kept(
    editor: TestClient, sample_database: Database
) -> None:
    created = _token(editor, name="  Copilot  ", expires_in_days=None)
    assert created["token"]["name"] == "Copilot" and created["token"]["expires_at"] is None
    listed = editor.get("/api/auth/tokens").json()
    assert listed == [created["token"]] and "secret" not in listed[0]
    with sample_database.session() as s:
        stored = s.scalars(select(ApiToken.token_hash)).all()
    assert created["secret"] not in stored and len(stored[0]) == 64


def test_what_a_new_token_may_be(editor: TestClient) -> None:
    for body in (
        {"name": ""},
        {"name": "x", "scope": "admin"},
        {"name": "x", "expires_in_days": 0},
        {"name": "x", "expires_in_days": 3651},
    ):
        assert editor.post("/api/auth/tokens", json=body).status_code == 422, body
    expires = _token(editor, expires_in_days=30)["token"]["expires_at"]
    assert expires.startswith((utcnow() + timedelta(days=30)).date().isoformat())


def test_at_most_so_many_live_tokens(editor: TestClient) -> None:
    for n in range(MAX_LIVE_TOKENS):
        _token(editor, name=f"t{n}")
    response = editor.post("/api/auth/tokens", json={"name": "one more"})
    assert response.status_code == 422 and "revoke" in response.json()["message"]
    first = editor.get("/api/auth/tokens").json()[-1]
    assert editor.delete(f"/api/auth/tokens/{first['id']}").status_code == 204
    _token(editor, name="one more")


def test_last_use_is_recorded(editor: TestClient, agent: TestClient) -> None:
    created = _token(editor)
    assert created["token"]["last_used_at"] is None
    _as(agent, created["secret"]).get("/api/tasks")
    used = editor.get("/api/auth/tokens").json()[0]
    assert used["last_used_at"] is not None and used["last_used_ip"] == "testclient"


def test_administrators_see_and_revoke_anyones_tokens(
    editor: TestClient, agent: TestClient, login_as: LoginAs, sample_database: Database
) -> None:
    _as(agent, _token(editor, name="Laptop agent")["secret"])
    stl = _user_id(sample_database, "stl")
    assert editor.get(f"/api/admin/users/{stl}/tokens").status_code == 403
    admin = login_as("admin")  # the same browser, now signed in as the administrator
    listed = admin.get(f"/api/admin/users/{stl}/tokens").json()
    assert [t["name"] for t in listed] == ["Laptop agent"]
    assert admin.delete(f"/api/admin/users/{stl}/tokens/{listed[0]['id']}").status_code == 204
    assert admin.get(f"/api/admin/users/{stl}/tokens").json() == []
    assert admin.get("/api/admin/users/99999/tokens").status_code == 404
    assert agent.get("/api/auth/me").status_code == 401
    actions = [e["action"] for e in admin.get("/api/admin/audit").json()]
    assert actions[0] == "token.revoked" and "token.created" in actions


def test_the_agent_guide(board: TestClient) -> None:
    response = board.get("/api/agent-guide")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    guide = response.text
    assert "Authorization: Bearer" in guide and "TASKBOARD_TOKEN" in guide
    assert "http://testserver/api/auth/me" in guide and "http://testserver/profile" in guide
    assert "{{" not in guide
    # Generated from the API: what an agent may use, with what it takes; nothing it may not.
    assert "- `POST /api/tasks`: New tasks start at the bottom of the ranking." in guide
    assert "`title`* string" in guide and "`status` idea|started|done|archived" in guide
    assert "- `GET /api/auth/me`" in guide
    for hidden in ("/api/admin/", "/api/auth/login", "/api/auth/tokens", "/api/auth/password"):
        assert hidden not in guide, hidden


def test_the_agent_guide_names_the_public_address(
    settings: Settings, sample_database: Database
) -> None:
    del sample_database
    public = settings.model_copy(update={"public_url": "https://tasks.example.com/taskboard"})
    with TestClient(create_app(public)) as client:
        guide = client.get("/api/agent-guide").text
    assert "https://tasks.example.com/taskboard/api/tasks" in guide
