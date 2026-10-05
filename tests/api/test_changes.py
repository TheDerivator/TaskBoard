"""Process changes API (milestone M12): lists with derived states, editing, periods, history.

The test settings pin today to the design's 3 Oct 2026, so the sample's states are the mockups'.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from taskboard.services.sample_data import defect_map_png
from tests.api.conftest import Ids, LoginAs
from tests.helpers import revoke_anonymous_access

PNG = defect_map_png(40, 20)
STL = "STL"


def _changes(client: TestClient, process: str) -> list[dict[str, Any]]:
    response = client.get("/api/changes", params={"process": process})
    assert response.status_code == 200, response.text
    return response.json()


def _by_key(client: TestClient, process: str) -> dict[str, dict[str, Any]]:
    return {c["key"]: c for c in _changes(client, process)}


@pytest.fixture
def stl_editor(login_as: LoginAs, ids: Ids) -> TestClient:
    """Editor for the whole STL department, so also for the processes owned by STL › Process."""
    return login_as("stl", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments[STL]))])


@pytest.fixture
def quality_editor(login_as: LoginAs, ids: Ids) -> TestClient:
    """Editor on STL › Quality only: may read process changes (anonymous floor), not edit them.

    The API fixtures share one client: request either this or `stl_editor`, not both."""
    return login_as("quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))])


# ---------------------------------------------------------------- reading


def test_the_ladle_metallurgy_list_matches_the_mockup(board: TestClient) -> None:
    """ChangesList.dc.html on 3 Oct 2026: newest first, and the "Now" column."""
    rows = _changes(board, "LM")
    assert [(r["key"], r["state"]["state"], r["state"]["date"]) for r in rows] == [
        ("LM-12", "planned", "2026-10-13"),
        ("LM-11", "test_running", "2026-10-03"),
        ("LM-10", "in_effect", "2026-08-01"),
        ("LM-09", "in_effect", "2026-05-12"),
        ("LM-08", "tests_ended", "2026-06-13"),
        ("LM-07", "in_effect", "2026-04-21"),
    ]


def test_a_change_lists_its_periods_in_order(board: TestClient) -> None:
    lm07 = _by_key(board, "LM")["LM-07"]
    assert lm07["url"] == "/changes/STL/LM/LM-07"
    assert lm07["post_count"] == 5  # three periods and two comments
    assert [(p["kind"], p["start_date"], p["end_date"], p["label"]) for p in lm07["periods"]] == [
        ("test", "2026-04-14", "2026-04-14", "Test"),
        ("test", "2026-04-16", "2026-04-16", "Follow-up test"),
        ("change", "2026-04-21", None, "Process change"),
    ]
    assert lm07["periods"][0]["scope_tags"] == ["IF-01", "Heats 41230–41236", "LF2"]


def test_the_other_processes(board: TestClient) -> None:
    cc = _by_key(board, "cc")  # codes ignore case
    assert cc["CC-34"]["state"] == {"state": "test_running", "date": "2026-10-09"}
    assert cc["CC-32"]["state"] == {"state": "tests_ended", "date": "2026-06-16"}
    assert [r["key"] for r in _changes(board, "CV")] == ["CV-24", "CV-23", "CV-22", "CV-21"]


def test_one_change_by_its_key(board: TestClient) -> None:
    change = board.get("/api/changes/lm-07").json()
    assert change["key"] == "LM-07" and change["title"] == "Argon stirring rate during trim"
    assert change["what_html"].startswith("<p>Argon flow during trim additions")
    assert change["permissions"] == {"edit": False, "comment": False, "delete": False}
    assert board.get("/api/changes/LM-99").status_code == 404


def test_who_may_read_process_changes(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    assert board.get("/api/changes", params={"process": "XX"}).status_code == 404
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get("/api/changes", params={"process": "LM"}).status_code == 401
    assert board.get("/api/changes/LM-07").status_code == 401
    # Rights on another section do not reach a process owned by STL › Process.
    login_as("coatings", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Coatings"]))])
    assert board.get("/api/changes", params={"process": "LM"}).status_code == 404
    assert board.get("/api/changes/LM-07").status_code == 404


# ---------------------------------------------------------------- editing


def test_new_changes_are_numbered_per_process(stl_editor: TestClient, ids: Ids) -> None:
    new = {"title": "Slag detection threshold", "owner_person_id": ids.people["AC"]}
    lm = stl_editor.post("/api/changes", json={**new, "process_id": ids.processes["LM"]})
    assert lm.status_code == 201, lm.text
    body = lm.json()
    assert body["key"] == "LM-13" and body["state"]["state"] == "no_periods"
    assert body["permissions"] == {"edit": True, "comment": True, "delete": False}
    cc = stl_editor.post("/api/changes", json={**new, "process_id": ids.processes["CC"]}).json()
    assert cc["key"] == "CC-35"


def test_creating_needs_edit_rights_in_the_owning_section(
    board: TestClient, quality_editor: TestClient, ids: Ids
) -> None:
    new = {"title": "X", "owner_person_id": ids.people["AC"], "process_id": ids.processes["LM"]}
    assert quality_editor.post("/api/changes", json=new).status_code == 403
    board.post("/api/auth/logout")
    assert board.post("/api/changes", json=new).status_code == 401


def test_change_input_is_checked(stl_editor: TestClient, ids: Ids) -> None:
    lm = ids.processes["LM"]
    blank = {"title": " ", "owner_person_id": ids.people["AC"], "process_id": lm}
    assert stl_editor.post("/api/changes", json=blank).status_code == 422
    nobody = {"title": "X", "owner_person_id": 999_999, "process_id": lm}
    assert stl_editor.post("/api/changes", json=nobody).status_code == 404
    nowhere = {"title": "X", "owner_person_id": ids.people["AC"], "process_id": 999_999}
    assert stl_editor.post("/api/changes", json=nowhere).status_code == 404


def test_editing_uses_the_version_last_read(stl_editor: TestClient, ids: Ids) -> None:
    change = stl_editor.get("/api/changes/LM-09").json()
    edited = stl_editor.patch(
        "/api/changes/LM-09",
        json={"version": change["version"], "why_md": "Fewer **skulls**.", "owner_person_id": 1},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["why_html"].strip() == "<p>Fewer <strong>skulls</strong>.</p>"
    assert edited.json()["version"] == change["version"] + 1
    stale = stl_editor.patch(
        "/api/changes/LM-09", json={"version": change["version"], "title": "Y"}
    )
    assert stale.status_code == 409


def test_a_change_moves_to_another_process_and_keeps_its_key(
    stl_editor: TestClient, login_as: LoginAs, ids: Ids
) -> None:
    version = stl_editor.get("/api/changes/LM-07").json()["version"]
    moved = stl_editor.patch(
        "/api/changes/LM-07", json={"version": version, "process_id": ids.processes["CC"]}
    ).json()
    assert moved["key"] == "LM-07" and moved["url"] == "/changes/STL/CC/LM-07"
    assert "LM-07" in _by_key(stl_editor, "CC")
    # Moving needs edit rights on both processes: R&D's process is out of this editor's reach.
    admin = login_as("admin")
    rd = admin.post(
        "/api/admin/processes",
        json={"code": "PC", "name": "Paint coating", "section_id": ids.sections["Coatings"]},
    ).json()
    editor = login_as("stl2", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments[STL]))])
    version = editor.get("/api/changes/LM-07").json()["version"]
    away = editor.patch("/api/changes/LM-07", json={"version": version, "process_id": rd["id"]})
    assert away.status_code == 403


def test_deleting_a_change_takes_its_conversation_along(
    stl_editor: TestClient, login_as: LoginAs
) -> None:
    assert stl_editor.delete("/api/changes/LM-07").status_code == 403  # Administrators only
    admin = login_as("admin")
    assert admin.delete("/api/changes/LM-07").status_code == 204
    assert admin.get("/api/changes/LM-07").status_code == 404
    assert "LM-07" not in _by_key(admin, "LM")


# ---------------------------------------------------------------- conversation and periods


def test_the_conversation_mixes_comments_and_periods(board: TestClient) -> None:
    conversation = board.get("/api/changes/LM-07/conversation").json()
    items = conversation["items"]
    assert [(i["author"]["display_name"], i["period"] is not None) for i in items] == [
        ("Anna Claes", True),
        ("Dries Wouters", False),
        ("Anna Claes", True),
        ("Chloé Martens", False),
        ("Anna Claes", True),
    ]
    assert conversation["can_comment"] is False and conversation["can_post_periods"] is False
    periods = board.get("/api/changes/LM-07/conversation", params={"periods_only": True}).json()
    assert [i["period"]["label"] for i in periods["items"]] == [
        "Test",
        "Follow-up test",
        "Process change",
    ]


def test_commenting_needs_change_comment(
    board: TestClient, stl_editor: TestClient, login_as: LoginAs
) -> None:
    posted = stl_editor.post("/api/changes/LM-07/posts", json={"body_md": "Looks good @Anna"})
    assert posted.status_code == 201, posted.text
    assert posted.json()["is_update"] is False and posted.json()["can_edit"] is True
    viewer = login_as("viewer", roles=[(BuiltinRole.VIEWER, Scope.everywhere())])
    assert viewer.post("/api/changes/LM-07/posts", json={"body_md": "Hi"}).status_code == 403
    board.post("/api/auth/logout")
    assert board.post("/api/changes/LM-07/posts", json={"body_md": "Hi"}).status_code == 401


def test_posting_periods(stl_editor: TestClient, login_as: LoginAs, ids: Ids) -> None:
    url = "/api/changes/LM-12/periods"
    no_end = {"kind": "test", "start_date": "2026-10-20"}
    assert stl_editor.post(url, json=no_end).status_code == 422
    backwards = {"kind": "test", "start_date": "2026-10-20", "end_date": "2026-10-19"}
    assert stl_editor.post(url, json=backwards).status_code == 422
    change = {
        "kind": "change",
        "start_date": "2026-09-01",
        "scope_tags": ["LF1", " lf1 ", "Heats  41300–41310"],
        "body_md": "Probe moved for good.",
    }
    posted = stl_editor.post(url, json=change)
    assert posted.status_code == 201, posted.text
    period = posted.json()["period"]
    assert period["label"] == "Process change" and period["end_date"] is None
    assert period["scope_tags"] == ["LF1", "Heats 41300–41310"]
    lm12 = _by_key(stl_editor, "LM")["LM-12"]
    assert lm12["state"] == {"state": "in_effect", "date": "2026-09-01"}
    # Posting periods is editing the change: editors of another section may not.
    quality = login_as(
        "quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    assert quality.post(url, json=change).status_code == 403


def test_set_end_date_keeps_the_earlier_version(stl_editor: TestClient) -> None:
    """Ending (reverting) LM-07's process change; DESIGN rule 6: "edited", history kept."""
    items = stl_editor.get("/api/changes/LM-07/conversation").json()["items"]
    post = next(i for i in items if i["period"] and i["period"]["kind"] == "change")
    ended = stl_editor.patch(
        f"/api/periods/{post['period']['id']}", json={"end_date": "2026-09-30"}
    )
    assert ended.status_code == 200, ended.text
    body = ended.json()
    assert body["period"]["end_date"] == "2026-09-30" and body["period"]["kind"] == "change"
    assert body["versions"] == 2 and body["edited_by"]["display_name"] == "Stl"
    assert _by_key(stl_editor, "LM")["LM-07"]["state"] == {"state": "ended", "date": "2026-09-30"}

    history = stl_editor.get(f"/api/posts/{post['id']}/history").json()
    assert [(v["rev"], v["written_by"]["display_name"]) for v in history] == [
        (1, "Anna Claes"),
        (2, "Stl"),
    ]
    assert history[0]["period"]["end_date"] is None
    assert history[1]["period"]["end_date"] == "2026-09-30"


def test_editing_periods_needs_change_edit(board: TestClient, quality_editor: TestClient) -> None:
    items = board.get("/api/changes/LM-07/conversation").json()["items"]
    period_id = items[0]["period"]["id"]
    assert quality_editor.patch(f"/api/periods/{period_id}", json={"label": "X"}).status_code == 403
    board.post("/api/auth/logout")
    assert board.patch(f"/api/periods/{period_id}", json={"label": "X"}).status_code == 401
    assert board.patch("/api/periods/999999", json={"label": "X"}).status_code in {401, 404}


def test_a_test_cannot_lose_its_end_date(stl_editor: TestClient) -> None:
    items = stl_editor.get("/api/changes/LM-07/conversation").json()["items"]
    period_id = items[0]["period"]["id"]
    assert stl_editor.patch(f"/api/periods/{period_id}", json={"end_date": None}).status_code == 422


def test_period_posts_are_edited_as_periods_and_deleted_by_editors(
    stl_editor: TestClient,
) -> None:
    items = stl_editor.get("/api/changes/LM-07/conversation").json()["items"]
    first = items[0]
    assert first["can_edit"] is True  # not the author, but may edit the change
    as_comment = stl_editor.patch(
        f"/api/posts/{first['id']}", json={"body_md": "x", "is_update": False}
    )
    assert as_comment.status_code == 422
    assert stl_editor.delete(f"/api/posts/{first['id']}").status_code == 204
    lm07 = _by_key(stl_editor, "LM")["LM-07"]
    assert len(lm07["periods"]) == 2 and lm07["post_count"] == 4


def test_comments_are_edited_by_their_author_with_history(stl_editor: TestClient) -> None:
    post = stl_editor.post("/api/changes/LM-07/posts", json={"body_md": "First"}).json()
    edited = stl_editor.patch(
        f"/api/posts/{post['id']}", json={"body_md": "Second", "is_update": True}
    )
    assert edited.status_code == 200
    assert edited.json()["is_update"] is False  # status updates are a task thing
    assert [v["body_md"] for v in stl_editor.get(f"/api/posts/{post['id']}/history").json()] == [
        "First",
        "Second",
    ]
    items = stl_editor.get("/api/changes/LM-07/conversation").json()["items"]
    dries = next(i for i in items if i["author"]["display_name"] == "Dries Wouters")
    assert dries["can_edit"] is False
    not_mine = stl_editor.patch(
        f"/api/posts/{dries['id']}", json={"body_md": "x", "is_update": False}
    )
    assert not_mine.status_code == 403


def test_scope_tags_already_used_are_suggested_most_used_first(board: TestClient) -> None:
    assert board.get("/api/processes/LM/scope-tags").json() == [
        "LF2",
        "All ULC grades",
        "CC2 sequences only",
        "Heats 41230–41236",
        "IF-01",
        "LF1",
    ]
    assert board.get("/api/processes/CC/scope-tags").json() == [
        "Caster 1 only",
        "First 3 heats of each sequence",
    ]
    assert board.get("/api/processes/XX/scope-tags").status_code == 404


def test_images_in_a_change_conversation_follow_its_visibility(
    board: TestClient, stl_editor: TestClient, sample_database: Database
) -> None:
    uploaded = stl_editor.post(
        "/api/changes/LM-07/attachments", files={"file": ("trend.png", PNG, "image/png")}
    )
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    posted = stl_editor.post(
        "/api/changes/LM-07/posts", json={"body_md": f"Trend:\n\n{image['markdown']}"}
    )
    assert f'src="{image["url"]}"' in posted.json()["html"]
    stl_editor.post("/api/auth/logout")
    assert board.get(f"/{image['url']}").status_code == 200  # anonymous may read LM
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get(f"/{image['url']}").status_code == 401
