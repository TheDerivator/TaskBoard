"""Releases of the FMEA and control plan (milestone M18): the sample's v1-v3 and draft, releasing,
old versions that stay as frozen, and who may release."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.api.conftest import Ids, LoginAs
from tests.helpers import revoke_anonymous_access


@pytest.fixture
def stl_editor(login_as: LoginAs, ids: Ids) -> TestClient:
    return login_as("stl", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))])


def _releases(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/processes/CC/releases")
    assert response.status_code == 200, response.text
    return response.json()


def _keys(client: TestClient, release: int | None = None) -> set[str]:
    params = {"release": release} if release else {}
    graph = client.get("/api/processes/CC/map", params=params).json()
    return {b["key"] for b in graph["boxes"]}


def _edit_control(client: TestClient, box: str, index: int, text: str) -> None:
    saved = client.get(f"/api/boxes/{box}").json()
    body = {k: saved["box"][k] for k in ("version", "kind", "name", "body_md", "main_url")}
    body |= {k: saved["box"][k] for k in ("facts", "fields", "step_no", "owner_person_id")}
    body["external_links"] = saved["box"]["external_links"]
    body["links"] = [
        {
            "id": lk["id"],
            "type": lk["type"],
            "direction": "forward" if lk["from_key"] == box else "backward",
            "to_key": lk["to_key"] if lk["from_key"] == box else lk["from_key"],
            "note_md": lk["note_md"],
        }
        for lk in saved["links"]
    ]
    body["controls"] = [
        {"id": c["id"], "kind": c["kind"], "text": c["text"], "external_links": c["external_links"]}
        for c in saved["controls"]
    ]
    body["controls"][index]["text"] = text
    response = client.patch(f"/api/boxes/{box}", json=body)
    assert response.status_code == 200, response.text


def test_the_sample_has_three_releases_and_the_mockups_draft(board: TestClient) -> None:
    data = _releases(board)
    assert [r["label"] for r in data["releases"]] == ["v3", "v2", "v1"]
    v3 = data["releases"][0]
    assert v3["released_by"]["display_name"] == "Anna Claes"
    assert v3["note"] == "After mould powder change CC-31"
    assert data["can_release"] is False
    draft = data["draft"]
    assert draft["base"] == 3
    entries = draft["entries"]
    assert [(e["box_key"], e["verb"]) for e in entries] == [
        ("fm-level", "changed"),
        ("fm-powder", "changed"),
        ("fm-clog", "changed"),
        ("fm-spray", "added"),
    ]
    assert (draft["fmea"], draft["cpl"]) == (4, 3)  # the release dialog's "4 affect FMEA, 3 CPL"
    assert draft["markers"] == {
        "fm-level": "Control changed since v3",
        "fm-powder": "Control added since v3",
        "fm-clog": "Link added since v3",
        "fm-spray": "New since v3",
    }
    [line] = entries[0]["lines"]
    assert (line["before"], line["after"]) == (1, 2)
    assert line["author"]["display_name"] == "Dries Wouters"
    assert line["summary"].startswith("Changed detect control: Alarm above [LIMIT]")
    assert entries[2]["documents"] == ["fmea"]  # a link between failure modes: not in the plan
    assert entries[3]["warnings"] == [
        "No controls yet: it will appear in the control plan without controls."
    ]
    assert entries[3]["lines"][0]["summary"] == "New, under Secondary cooling › Spray zones"


def test_old_versions_are_drawn_from_what_they_froze(board: TestClient) -> None:
    v1, v2, v3 = _keys(board, 1), _keys(board, 2), _keys(board, 3)
    assert "fm-osc" not in v1 and "fm-burr" not in v1  # v2 added oscillation and cutting
    assert {"m-osc", "fm-osc", "cut", "fm-burr"} <= v2
    assert "fm-spray" not in v3 and "sec-spray" not in v3 and "fm-spray" in _keys(board)
    assert "overview" not in v3  # knowledge stays out of releases
    graph = board.get("/api/processes/CC/map", params={"release": 3}).json()
    assert graph["can_edit"] is False and graph["change_counts"] == {}
    level = [c["text"] for c in graph["controls"] if c["box_key"] == "fm-level"]
    assert level[2].startswith("Alarm above [OLD LIMIT]")
    assert [c["kind"] for c in graph["controls"] if c["box_key"] == "fm-powder"] == ["detect"]
    plan = board.get(
        "/api/control-plan", params={"department": "STL", "process": "CC", "release": 3}
    ).json()
    defects = [b["key"] for b in plan["boxes"] if b["process_id"] is None]
    assert "d-corner" not in defects and "d-sliver" in defects  # spray cooling came after v3
    assert plan["defect_sections"] == []
    assert board.get("/api/processes/CC/map", params={"release": 9}).status_code == 404
    missing_process = {"department": "STL", "release": 3}
    assert board.get("/api/control-plan", params=missing_process).status_code == 422


def test_releasing_the_draft(stl_editor: TestClient) -> None:
    before_v3 = stl_editor.get("/api/processes/CC/map", params={"release": 3}).json()
    response = stl_editor.post("/api/processes/CC/releases", json={"note": "Spray", "base": 3})
    assert response.status_code == 201, response.text
    assert response.json()["label"] == "v4"
    data = _releases(stl_editor)
    assert data["can_release"] is True
    assert data["draft"]["base"] == 4 and data["draft"]["entries"] == []
    assert "fm-spray" in _keys(stl_editor, 4)
    # Nothing new to release; a release based on an older version is refused.
    again = stl_editor.post("/api/processes/CC/releases", json={"note": "", "base": 4})
    assert again.status_code == 422
    stale = stl_editor.post("/api/processes/CC/releases", json={"note": "", "base": 3})
    assert stale.status_code == 409
    # Later edits and deletions leave the released versions as they were.
    _edit_control(stl_editor, "fm-level", 2, "Alarm above [NEWER LIMIT] mm fluctuation")
    assert stl_editor.delete("/api/boxes/fm-burr").status_code == 204
    assert stl_editor.get("/api/processes/CC/map", params={"release": 3}).json() == before_v3
    entries = _releases(stl_editor)["draft"]["entries"]
    assert [(e["box_key"], e["verb"]) for e in entries] == [
        ("fm-level", "changed"),
        ("fm-burr", "removed"),
    ]


def test_knowledge_edits_stay_out_of_the_draft(stl_editor: TestClient) -> None:
    saved = stl_editor.get("/api/boxes/k-osc").json()["box"]
    body = {k: saved[k] for k in ("version", "kind", "name", "main_url", "facts", "fields")}
    body |= {"body_md": "Edited.", "step_no": None, "owner_person_id": saved["owner_person_id"]}
    body["external_links"] = []
    body["links"] = [{"type": "explains", "to_key": "fm-osc", "direction": "forward"}]
    response = stl_editor.patch("/api/boxes/k-osc", json=body)
    assert response.status_code == 200, response.text
    draft = _releases(stl_editor)["draft"]
    assert [e["box_key"] for e in draft["entries"]] == [
        "fm-level",
        "fm-powder",
        "fm-clog",
        "fm-spray",
    ]
    assert draft["outside_scope"] >= 1


def test_who_may_release(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    viewer = login_as(
        "viewer", roles=[(BuiltinRole.VIEWER, Scope.department(ids.departments["STL"]))]
    )
    assert viewer.post("/api/processes/CC/releases", json={"base": 3}).status_code == 403
    viewer.post("/api/auth/logout")
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get("/api/processes/CC/releases").status_code == 401
    assert board.post("/api/processes/CC/releases", json={"base": 3}).status_code in (401, 403)
