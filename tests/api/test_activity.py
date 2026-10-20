"""Recent activity API (milestone M25): tasks and process changes by their newest post, filters,
pages without repeats, and only what you may see."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import update

from taskboard.db.models import User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Permission, Scope
from tests.api.conftest import Ids, LoginAs
from tests.helpers import login, make_role, make_user, revoke_anonymous_access

# The sample's tasks with posts, newest post first (T-117, T-126 and T-062 have none).
TASKS_BY_ACTIVITY = ["121", "130", "089", "098", "133", "104", "110", "075"]


def keys(body: dict[str, Any]) -> list[str]:
    return [i["task"]["key"] if i["type"] == "task" else i["change"]["key"] for i in body["items"]]


def activity(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/api/activity", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_tasks_by_their_newest_post(board: TestClient) -> None:
    body = activity(board, types="task")
    assert keys(body) == TASKS_BY_ACTIVITY
    assert body["next"] is None
    newest, update = body["items"][0], body["items"][1]
    assert newest["task"]["ref"] == "T-121" and newest["task"]["url"] == "/t/121"
    assert newest["post_count"] == 2
    assert newest["last_post"]["kind"] == "comment"
    assert newest["last_post"]["author"]["display_name"] == "Bram Peeters"
    assert newest["last_post"]["excerpt"].startswith(
        "The third quote is in. Comparison table: camera-quotes.xlsx."  # Markdown marks gone
    )
    assert update["task"]["key"] == "130" and update["post_count"] == 3
    assert update["last_post"]["kind"] == "update"
    assert update["last_post"]["excerpt"] == (
        "Week 40 status · All panels pass cross-hatch class 0. Report drafted; review with R&D"
        " on Monday."
    )


def test_only_new_posts_count(login_as: LoginAs) -> None:
    """Lifecycle changes (events) and edits of older posts leave the order as it was."""
    client = login_as("admin")
    t075 = client.get("/api/tasks/T-075").json()
    patched = client.patch("/api/tasks/T-075", json={"version": t075["version"], "status": "idea"})
    assert patched.status_code == 200
    assert keys(activity(client, types="task")) == TASKS_BY_ACTIVITY

    post = client.post("/api/tasks/T-110/posts", json={"body_md": "Checked again."}).json()
    assert keys(activity(client, types="task"))[:2] == ["110", "121"]
    client.post("/api/tasks/T-075/posts", json={"body_md": "Reopened for **one** more look."})
    edited = client.patch(f"/api/posts/{post['id']}", json={"body_md": "Typo", "is_update": False})
    assert edited.status_code == 200
    body = activity(client, types="task")
    assert keys(body)[:3] == ["075", "110", "121"]
    assert body["items"][0]["last_post"]["excerpt"] == "Reopened for one more look."
    assert body["items"][0]["last_post"]["author"]["display_name"] == "Administrator"

    client.post("/api/tasks/T-117/posts", json={"body_md": "A first post.", "is_update": True})
    first = activity(client, types="task")["items"][0]
    assert first["task"]["key"] == "117" and first["last_post"]["kind"] == "update"


def test_process_changes_are_listed_with_tasks(board: TestClient) -> None:
    body = activity(board, limit=100)
    assert {i["type"] for i in body["items"]} == {"task", "change"}
    times = [i["last_post"]["created_at"] for i in body["items"]]
    assert times == sorted(times, reverse=True)
    assert [k for k in keys(body) if not k[0].isalpha()] == TASKS_BY_ACTIVITY

    changes = activity(board, types="change", limit=100)
    assert {i["type"] for i in changes["items"]} == {"change"}
    lm07 = next(i for i in changes["items"] if i["change"]["key"] == "LM-07")
    assert lm07["post_count"] == 5  # three periods and two comments
    assert lm07["last_post"]["kind"] == "period"
    assert lm07["change"]["url"] == "/changes/STL/LM/LM-07"


def test_a_project_or_one_of_its_sections_lists_its_tasks(board: TestClient, ids: Ids) -> None:
    """Process changes sit in no project: a project lists tasks only, whatever the types."""
    assert keys(activity(board, project_id=ids.projects["ASQ"])) == [
        "121",
        "089",
        "098",
        "104",
        "075",
    ]
    assert keys(activity(board, node_id=ids.nodes["ASQ:2"])) == ["098", "104", "075"]
    assert keys(activity(board, project_id=ids.projects["SAF"], types="change")) == []


def test_organization_and_process_filters(board: TestClient, ids: Ids) -> None:
    assert keys(activity(board, department_id=ids.departments["R&D"])) == ["130"]
    quality = activity(board, section_id=ids.sections["Quality"])
    assert keys(quality) == ["089", "104", "075"]  # Quality owns no process
    process = activity(board, section_id=ids.sections["Process"], limit=100)
    assert [k for k in keys(process) if not k[0].isalpha()] == ["121", "133"]
    assert any(i["type"] == "change" for i in process["items"])  # the processes' owning section

    lm = activity(board, process_id=ids.processes["LM"], limit=100)
    assert lm["items"] and {i["type"] for i in lm["items"]} == {"change"}
    assert {k.split("-")[0] for k in keys(lm)} == {"LM"}
    both = activity(board, process_id=ids.processes["LM"], department_id=ids.departments["R&D"])
    assert keys(both) == []


def test_pages_follow_each_other_without_repeats(login_as: LoginAs) -> None:
    client = login_as("admin")
    first = activity(client, limit=2)
    assert len(first["items"]) == 2 and first["next"]
    # A new post moves T-075 to the top: the older pages no longer hold it, nothing shows twice.
    client.post("/api/tasks/T-075/posts", json={"body_md": "One more thing."})
    seen, cursor = keys(first), first["next"]
    while cursor:
        page = activity(client, limit=2, before=cursor)
        assert len(page["items"]) <= 2
        seen += keys(page)
        cursor = page["next"]
    everything = keys(activity(client, limit=100))
    assert len(seen) == len(set(seen))
    assert everything[0] == "075"
    assert seen == [k for k in everything if k != "075"]


def test_wrong_requests_are_refused(board: TestClient) -> None:
    for params in (
        {"before": "yesterday"},
        {"before": "9999999999999999999-1"},  # far beyond any date
        {"limit": 0},
        {"limit": 101},
        {"types": "box"},
    ):
        assert board.get("/api/activity", params=params).status_code == 422, params


def test_only_what_you_may_see(board: TestClient, sample_database: Database, ids: Ids) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
        make_role(s, "change-reader", [Permission.CHANGE_VIEW])
        make_user(
            s, "coatings", roles=[(BuiltinRole.VIEWER, Scope.section(ids.sections["Coatings"]))]
        )
        make_user(
            s, "process", roles=[(BuiltinRole.VIEWER, Scope.section(ids.sections["Process"]))]
        )
        make_user(s, "changes", roles=[("change-reader", Scope.section(ids.sections["Process"]))])
        make_user(s, "nobody")
    assert board.get("/api/activity").status_code == 401

    assert login(board, "coatings").status_code == 200
    assert keys(activity(board)) == ["130"]  # Coatings owns no process either
    assert login(board, "process").status_code == 200
    process = keys(activity(board, limit=100))
    assert [k for k in process if not k[0].isalpha()] == ["121", "133"]
    assert login(board, "changes").status_code == 200
    changes = activity(board, limit=100)
    assert changes["items"] and {i["type"] for i in changes["items"]} == {"change"}
    assert activity(board, types="task")["items"] == []  # a type you may not see is left out
    assert login(board, "nobody").status_code == 200
    assert activity(board) == {"items": [], "next": None}


def test_a_pending_password_change_blocks_activity(
    login_as: LoginAs, sample_database: Database
) -> None:
    client = login_as("admin")
    with sample_database.session(write=True) as s:
        s.execute(update(User).where(User.username == "admin").values(must_change_password=True))
    response = client.get("/api/activity")
    assert response.status_code == 403
    assert response.json()["error"] == "password_change_required"
