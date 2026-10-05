"""Process knowledge API (milestone M14): maps, saving boxes with revisions, the tree, history,
references from changes and tasks, and the kinds & link types settings."""

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from taskboard.config import Settings
from taskboard.db.models import Attachment
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Permission, Scope
from taskboard.services.sample_data import defect_map_png
from tests.api.conftest import Ids, LoginAs
from tests.helpers import (
    assert_revisions_match_rows,
    login,
    make_role,
    make_user,
    revoke_anonymous_access,
)

PNG = defect_map_png(40, 20)

# The ProcessMap mockup's tree: each box and its parent.
CC_TREE = {
    "cc": None,
    "overview": "cc",
    "speeds": "cc",
    "plan": "cc",
    "r-peri": "plan",
    "r-tund": "plan",
    "r-width": "plan",
    "tun": "cc",
    "tun-flow": "tun",
    "fm-clog": "tun-flow",
    "tun-slag": "tun",
    "fm-slag": "tun-slag",
    "mould": "cc",
    "m-level": "mould",
    "fm-level": "m-level",
    "m-powder": "mould",
    "fm-powder": "m-powder",
    "ref-powder": "m-powder",
    "m-osc": "mould",
    "k-osc": "m-osc",
    "fm-osc": "m-osc",
    "sec": "cc",
    "sec-spray": "sec",
    "fm-spray": "sec-spray",
    "bow": "cc",
    "bow-unb": "bow",
    "fm-duct": "bow-unb",
    "cut": "cc",
    "cut-torch": "cut",
    "fm-burr": "cut-torch",
}


@pytest.fixture
def stl_editor(login_as: LoginAs, ids: Ids) -> TestClient:
    """Editor for STL: its processes' maps (STL › Process) and its defects (STL › Quality)."""
    return login_as("stl", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))])


def _box(client: TestClient, key: str) -> dict[str, Any]:
    response = client.get(f"/api/boxes/{key}")
    assert response.status_code == 200, response.text
    return response.json()


def _content(saved: dict[str, Any], **changes: Any) -> dict[str, Any]:
    """The editor's payload for a box as it is, with `changes` applied."""
    box = saved["box"]
    body = {
        "version": box["version"],
        "kind": box["kind"],
        "name": box["name"],
        "body_md": box["body_md"],
        "main_url": box["main_url"],
        "facts": box["facts"],
        "fields": box["fields"],
        "step_no": box["step_no"],
        "owner_person_id": box["owner_person_id"],
        "external_links": [
            {k: e[k] for k in ("kind", "label", "url", "pass_box_param")}
            for e in box["external_links"]
        ],
        "links": [
            {
                "id": lk["id"],
                "type": lk["type"],
                "to_key": lk["to_key"] if lk["from_key"] == box["key"] else lk["from_key"],
                "direction": "forward" if lk["from_key"] == box["key"] else "backward",
                "note_md": lk["note_md"],
            }
            for lk in saved["links"]
        ],
        "controls": [
            {
                "id": c["id"],
                "kind": c["kind"],
                "text": c["text"],
                "external_links": [
                    {k: e[k] for k in ("kind", "label", "url", "pass_box_param")}
                    for e in c["external_links"]
                ],
            }
            for c in saved["controls"]
        ],
    }
    return body | changes


# ---------------------------------------------------------------- reading


def test_the_continuous_casting_map(board: TestClient) -> None:
    graph = board.get("/api/processes/cc/map").json()
    assert graph["process"]["code"] == "CC" and graph["root_key"] == "cc"
    in_map = {b["key"]: b["parent_key"] for b in graph["boxes"] if b["process_id"] is not None}
    assert in_map == CC_TREE
    defects = sorted(b["key"] for b in graph["boxes"] if b["process_id"] is None)
    assert defects == [
        "d-blisters",
        "d-corner",
        "d-edge",
        "d-incl",
        "d-long",
        "d-sliver",
        "d-trans",
    ]
    assert len(graph["links"]) == 17 and len(graph["controls"]) == 9
    assert graph["change_counts"] == {"m-powder": 1, "m-level": 1, "sec-spray": 1, "tun-flow": 1}
    assert graph["can_edit"] is False
    assert [k["key"] for k in graph["kinds"]] == ["step", "know", "ref", "rule", "fm", "defect"]
    mould = next(b for b in graph["boxes"] if b["key"] == "mould")
    assert mould["external_links"][0]["href"] == "https://grafana.plant.local/d/mould?node=mould"


def test_a_box_with_its_links_both_ways_and_its_controls(board: TestClient) -> None:
    saved = _box(board, "fm-level")
    assert saved["box"]["kind"] == "fm" and saved["box"]["body_html"].startswith("<p>Waves")
    links = {(lk["from_key"], lk["type"], lk["to_key"]) for lk in saved["links"]}
    assert links == {
        ("fm-level", "leads_to", "d-sliver"),
        ("fm-level", "leads_to", "d-long"),
        ("fm-clog", "leads_to", "fm-level"),
        ("r-peri", "prevents", "fm-level"),
    }
    assert [(c["kind"], len(c["external_links"])) for c in saved["controls"]] == [
        ("prevent", 1),
        ("prevent", 1),
        ("detect", 1),
    ]


def test_a_process_without_a_map(board: TestClient) -> None:
    graph = board.get("/api/processes/LM/map").json()
    assert graph["root_key"] is None
    assert not any(b["process_id"] == graph["process"]["id"] for b in graph["boxes"])
    # Still there: the department's defects (and the boxes elsewhere that lead to them).
    assert {b["key"] for b in graph["boxes"] if b["process_id"] is None} >= {"d-sliver", "d-edge"}


def test_who_may_read_process_knowledge(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    assert board.get("/api/processes/XX/map").status_code == 404
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get("/api/processes/CC/map").status_code == 401
    assert board.get("/api/boxes/fm-level").status_code == 401
    login_as("coatings", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Coatings"]))])
    assert board.get("/api/processes/CC/map").status_code == 404
    assert board.get("/api/boxes/fm-level").status_code == 404


# ---------------------------------------------------------------- saving


def test_a_new_box_under_another(stl_editor: TestClient, sample_database: Database) -> None:
    created = stl_editor.post(
        "/api/boxes",
        json={
            "parent_key": "m-level",
            "kind": "know",
            "name": "Level sensor principle",
            "body_md": "Eddy currents.",
            "facts": [["Range", "0–150 mm"]],
            "links": [{"type": "explains", "to_key": "fm-level"}],
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["box"]["key"] == "level-sensor-principle" and body["box"]["rev"] == 1
    assert body["box"]["parent_key"] == "m-level" and body["box"]["facts"] == [
        ["Range", "0–150 mm"]
    ]
    assert body["links"][0]["to_key"] == "fm-level"
    again = stl_editor.post(
        "/api/boxes",
        json={"parent_key": "m-level", "kind": "know", "name": "Level sensor principle"},
    )
    assert again.json()["box"]["key"] == "level-sensor-principle-2"
    with sample_database.session() as s:
        assert_revisions_match_rows(s)


def test_editing_needs_rights_in_the_owning_section(
    board: TestClient, login_as: LoginAs, ids: Ids
) -> None:
    new = {"parent_key": "m-level", "kind": "know", "name": "X"}
    assert board.post("/api/boxes", json=new).status_code == 401
    quality = login_as(
        "quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    assert quality.post("/api/boxes", json=new).status_code == 403  # the map is STL › Process's
    # Quality owns the sample's defects, so its editors may add one there.
    defect = {"kind": "defect", "name": "Scale pits", "section_id": ids.sections["Quality"]}
    assert (
        quality.post("/api/boxes", json=defect | {"fields": {"group": "Surface"}}).status_code
        == 201
    )


def test_box_input_is_checked(stl_editor: TestClient, ids: Ids) -> None:
    base = {"parent_key": "m-level", "kind": "know", "name": "X"}
    assert stl_editor.post("/api/boxes", json=base | {"kind": "nope"}).status_code == 404
    assert stl_editor.post("/api/boxes", json=base | {"parent_key": "nope"}).status_code == 404
    defect_in_tree = base | {"kind": "defect"}
    assert stl_editor.post("/api/boxes", json=defect_in_tree).status_code == 422
    no_section = {"kind": "defect", "name": "Y"}
    assert stl_editor.post("/api/boxes", json=no_section).status_code == 422
    unknown_field = {
        "kind": "defect",
        "name": "Y",
        "section_id": ids.sections["Quality"],
        "fields": {"grup": "x"},
    }
    assert stl_editor.post("/api/boxes", json=unknown_field).status_code == 422
    script = base | {
        "external_links": [{"kind": "document", "label": "x", "url": "javascript:alert(1)"}]
    }
    assert stl_editor.post("/api/boxes", json=script).status_code == 422
    controls_on_knowledge = base | {"controls": [{"kind": "prevent", "text": "x"}]}
    assert stl_editor.post("/api/boxes", json=controls_on_knowledge).status_code == 422
    self_link = {"type": "see_also", "to_key": "nope"}
    assert stl_editor.post("/api/boxes", json=base | {"links": [self_link]}).status_code == 404


def test_saving_writes_a_revision_per_changed_object(
    stl_editor: TestClient, sample_database: Database
) -> None:
    saved = _box(stl_editor, "fm-level")
    controls = _content(saved)["controls"]
    controls[2]["text"] = "Alarm above [NEW LIMIT] mm fluctuation"  # the mockup's v4 change
    controls.append({"kind": "prevent", "text": "Argon flow capped at sequence start"})
    del controls[1]  # the calibration control goes
    links = _content(saved)["links"] + [
        {"type": "leads_to", "to_key": "d-blisters", "note_md": "Rarely."}
    ]
    response = stl_editor.patch(
        "/api/boxes/fm-level", json=_content(saved, controls=controls, links=links)
    )
    assert response.status_code == 200, response.text
    after = response.json()
    assert after["box"]["rev"] == saved["box"]["rev"]  # the box itself did not change
    texts = [(c["text"], c["rev"]) for c in after["controls"]]
    assert texts == [
        ("Level control loop tuned per slab format", 1),
        ("Alarm above [NEW LIMIT] mm fluctuation", 3),  # the sample edited it once after v3
        ("Argon flow capped at sequence start", 1),
    ]
    history = stl_editor.get("/api/boxes/fm-level/history").json()
    summaries = [h["summary"] for h in history[:4]]
    assert "Removed prevent control: Level sensor calibrated every [INTERVAL]" in summaries
    assert "Added link: leads to Blisters" in summaries
    with sample_database.session() as s:
        assert_revisions_match_rows(s)


def test_a_stale_save_is_refused(stl_editor: TestClient) -> None:
    saved = _box(stl_editor, "mould")
    first = stl_editor.patch("/api/boxes/mould", json=_content(saved, body_md="New text."))
    assert first.status_code == 200 and first.json()["box"]["rev"] == 2
    stale = stl_editor.patch("/api/boxes/mould", json=_content(saved, body_md="Other text."))
    assert stale.status_code == 409
    changes = [h["changed"] for h in stl_editor.get("/api/boxes/mould/history").json()]
    assert changes[0] == ["body_md"]


def test_moving_within_the_map(stl_editor: TestClient, sample_database: Database) -> None:
    moved = stl_editor.post(
        "/api/boxes/ref-powder/move", json={"parent_key": "mould", "before_key": "m-osc"}
    )
    assert moved.status_code == 200, moved.text
    graph = stl_editor.get("/api/processes/CC/map").json()
    order = [
        b["key"]
        for b in sorted(
            (b for b in graph["boxes"] if b["parent_key"] == "mould"), key=lambda b: b["position"]
        )
    ]
    assert order == ["m-level", "m-powder", "ref-powder", "m-osc"]
    assert (
        stl_editor.post("/api/boxes/tun/move", json={"parent_key": "tun-flow"}).status_code == 422
    )
    assert stl_editor.post("/api/boxes/cc/move", json={"parent_key": "mould"}).status_code == 422
    assert (
        stl_editor.post("/api/boxes/d-sliver/move", json={"parent_key": "mould"}).status_code == 422
    )
    with sample_database.session() as s:
        assert_revisions_match_rows(s)


def test_deleting_a_box(stl_editor: TestClient, sample_database: Database) -> None:
    assert stl_editor.delete("/api/boxes/m-level").status_code == 409  # fm-level is under it
    assert stl_editor.delete("/api/boxes/fm-level").status_code == 204
    assert stl_editor.get("/api/boxes/fm-level").status_code == 404
    graph = stl_editor.get("/api/processes/CC/map").json()
    assert not any("fm-level" in (lk["from_key"], lk["to_key"]) for lk in graph["links"])
    assert len(graph["controls"]) == 6
    with sample_database.session() as s:
        assert_revisions_match_rows(s)  # every removed link and control has a deletion revision


def test_starting_a_map(stl_editor: TestClient, board: TestClient) -> None:
    started = stl_editor.post("/api/processes/LM/map")
    assert started.status_code == 201 and started.json()["key"] == "ladle-metallurgy"
    assert stl_editor.post("/api/processes/LM/map").status_code == 409
    child = stl_editor.post(
        "/api/boxes",
        json={"parent_key": "ladle-metallurgy", "kind": "step", "name": "Trim & stirring"},
    )
    assert child.json()["box"]["key"] == "trim-stirring"
    stl_editor.post("/api/auth/logout")
    assert board.post("/api/processes/CV/map").status_code == 401


def test_marking_a_box_reviewed(stl_editor: TestClient) -> None:
    reviewed = stl_editor.post("/api/boxes/overview/reviewed").json()
    assert reviewed["box"]["reviewed_at"] == "2026-10-03" and reviewed["box"]["rev"] == 2


# ---------------------------------------------------------------- references


def test_where_changes_and_tasks_sit_in_the_map(board: TestClient) -> None:
    refs = board.get("/api/changes/CC-31/boxes").json()
    assert [(r["key"], r["path"]) for r in refs] == [("m-powder", ["Continuous casting", "Mould"])]
    assert [r["key"] for r in board.get("/api/tasks/104/boxes").json()] == ["fm-level"]


def test_a_change_shows_on_its_box_and_every_box_above_it(board: TestClient) -> None:
    mould = board.get("/api/boxes/mould/related").json()
    assert [(c["key"], c["box_key"]) for c in mould["changes"]] == [
        ("CC-31", "m-powder"),
        ("CC-32", "m-level"),
    ]
    assert mould["changes"][0]["state"] == "in_effect"
    assert {c["key"] for c in board.get("/api/boxes/cc/related").json()["changes"]} == {
        "CC-31",
        "CC-32",
        "CC-33",
        "CC-34",
    }
    assert [t["ref"] for t in board.get("/api/boxes/fm-level/related").json()["tasks"]] == ["T-104"]


def test_linking_a_change_to_the_map(stl_editor: TestClient, login_as: LoginAs, ids: Ids) -> None:
    linked = stl_editor.put("/api/changes/LM-11/boxes/fm-clog")  # across processes
    assert linked.status_code == 200 and [r["key"] for r in linked.json()] == ["fm-clog"]
    assert stl_editor.put("/api/changes/LM-11/boxes/fm-clog").status_code == 200  # idempotent
    assert {c["key"] for c in stl_editor.get("/api/boxes/tun/related").json()["changes"]} == {
        "CC-34",
        "LM-11",
    }
    assert stl_editor.delete("/api/changes/LM-11/boxes/fm-clog").json() == []
    quality = login_as(
        "quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    assert quality.put("/api/changes/LM-11/boxes/fm-clog").status_code == 403  # needs change.edit


def test_linking_a_task_needs_task_edit(board: TestClient, login_as: LoginAs, ids: Ids) -> None:
    assert board.put("/api/tasks/104/boxes/mould").status_code == 401
    quality = login_as(
        "quality", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Quality"]))]
    )
    linked = quality.put("/api/tasks/104/boxes/mould")  # T-104 is a Quality task
    assert linked.status_code == 200
    assert {r["key"] for r in linked.json()} == {"fm-level", "mould"}


# ---------------------------------------------------------------- settings


def test_kinds_and_link_types_are_configured_by_administrators(
    board: TestClient, login_as: LoginAs
) -> None:
    settings = board.get("/api/map-settings").json()
    assert {k["key"]: k["box_count"] for k in settings["kinds"]}["fm"] == 8
    assert settings["can_configure"] is False
    editor = login_as("editor", roles=[(BuiltinRole.EDITOR, Scope.everywhere())])
    assert editor.post("/api/box-kinds", json={"name": "Work element"}).status_code == 403
    admin = login_as("admin")
    created = admin.post(
        "/api/box-kinds",
        json={
            "name": "Work element",
            "style": "teal",
            "field_schema": [{"key": "m4", "label": "4M"}],
        },
    )
    assert created.status_code == 201, created.text
    kind = next(k for k in created.json()["kinds"] if k["key"] == "work_element")
    assert kind["role"] == "plain" and kind["field_schema"][0]["key"] == "m4"
    assert admin.post("/api/box-kinds", json={"name": "X", "style": "neon"}).status_code == 422
    assert admin.delete("/api/box-kinds/fm").status_code == 422  # built in
    assert admin.delete("/api/box-kinds/work_element").status_code == 200
    renamed = admin.patch("/api/link-types/see_also", json={"forward_name": "related to"})
    assert (
        next(t for t in renamed.json()["link_types"] if t["key"] == "see_also")["forward_name"]
        == "related to"
    )
    made = admin.post(
        "/api/link-types", json={"forward_name": "measured by", "backward_name": "measures"}
    )
    assert made.status_code == 201
    assert admin.delete("/api/link-types/leads_to").status_code == 422


def test_deleting_a_task_or_change_drops_its_references(login_as: LoginAs) -> None:
    admin = login_as("admin")
    assert admin.delete("/api/tasks/104").status_code == 204  # T-104 is about fm-level
    assert admin.delete("/api/changes/CC-31").status_code == 204  # CC-31 affects m-powder
    related = admin.get("/api/boxes/fm-level/related").json()
    assert related["tasks"] == []
    assert "CC-31" not in {
        c["key"] for c in admin.get("/api/boxes/mould/related").json()["changes"]
    }


def test_a_process_with_a_map_and_a_section_with_defects_stay(login_as: LoginAs, ids: Ids) -> None:
    admin = login_as("admin")
    lm = ids.processes["LM"]
    admin.post("/api/processes/LM/map")
    for key in ("LM-07", "LM-08", "LM-09", "LM-10", "LM-11", "LM-12"):
        admin.delete(f"/api/changes/{key}")
    refused = admin.delete(f"/api/admin/processes/{lm}")
    assert refused.status_code == 409 and "knowledge map" in refused.json()["message"]
    quality = admin.delete(f"/api/admin/sections/{ids.sections['Quality']}")
    assert quality.status_code == 409 and "defects" in quality.json()["message"]


# ---------------------------------------------------------------- pickers and images


def test_finding_boxes_for_the_link_pickers(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    found = board.get("/api/boxes", params={"q": "MOULD L"}).json()
    assert [(r["key"], r["path"]) for r in found] == [
        ("m-level", ["Continuous casting", "Mould"]),
        ("fm-level", ["Continuous casting", "Mould", "Mould level control"]),
    ]
    assert [r["key"] for r in board.get("/api/boxes", params={"q": "sliver"}).json()] == [
        "d-sliver"
    ]
    assert board.get("/api/boxes", params={"q": " "}).json() == []
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    login_as("coatings", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Coatings"]))])
    assert board.get("/api/boxes", params={"q": "mould"}).json() == []


def test_a_change_lists_where_it_sits_in_the_map(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    changes = {c["key"]: c for c in board.get("/api/changes", params={"process": "CC"}).json()}
    assert changes["CC-31"]["box_keys"] == ["m-powder"]
    assert changes["CC-33"]["box_keys"] == ["sec-spray"]
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
        make_role(s, "change-reader", [Permission.CHANGE_VIEW])
        make_user(s, "reader", roles=[("change-reader", Scope.everywhere())])
    login(board, "reader")
    unseen = {c["key"]: c for c in board.get("/api/changes", params={"process": "CC"}).json()}
    assert unseen["CC-31"]["box_keys"] == []  # no knowledge rights: the map stays hidden


def test_images_in_a_box_description(
    stl_editor: TestClient, board: TestClient, sample_database: Database, settings: Settings
) -> None:
    uploaded = stl_editor.post(
        "/api/boxes/mould/attachments", files={"file": ("section.png", PNG, "image/png")}
    )
    assert uploaded.status_code == 201, uploaded.text
    image = uploaded.json()
    saved = _box(stl_editor, "mould")
    stl_editor.patch(
        "/api/boxes/mould", json=_content(saved, body_md=f"Cross-section:\n\n{image['markdown']}")
    )
    assert f'src="{image["url"]}"' in _box(stl_editor, "mould")["box"]["body_html"]
    # Days later a conversation upload clears unposted drafts; a box's images are not drafts.
    with sample_database.new_session(write=True) as s:
        s.execute(update(Attachment).values(created_at=datetime(2026, 1, 1, tzinfo=UTC)))
        s.commit()
    stl_editor.post("/api/tasks/104/attachments", files={"file": ("x.png", PNG, "image/png")})
    stl_editor.post("/api/auth/logout")
    assert board.get(f"/{image['url']}").status_code == 200  # visitors may read the map
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get(f"/{image['url']}").status_code == 401
    assert (settings.uploads_dir / image["id"]).exists()


def test_box_images_need_edit_rights(board: TestClient) -> None:
    response = board.post(
        "/api/boxes/mould/attachments", files={"file": ("a.png", PNG, "image/png")}
    )
    assert response.status_code == 401


def test_links_are_edited_from_either_end(
    stl_editor: TestClient, sample_database: Database
) -> None:
    """fm-level "caused by" fm-clog is fm-clog's link; editing fm-level may change it too."""
    saved = _box(stl_editor, "fm-level")
    links = _content(saved)["links"]
    caused_by = next(lk for lk in links if lk["to_key"] == "fm-clog")
    assert caused_by["direction"] == "backward"
    caused_by["note_md"] = "A clog that breaks loose makes the level jump."
    links.append({"type": "explains", "to_key": "k-osc", "direction": "backward"})
    after = stl_editor.patch("/api/boxes/fm-level", json=_content(saved, links=links)).json()
    pairs = {(lk["from_key"], lk["type"], lk["to_key"], lk["rev"]) for lk in after["links"]}
    assert ("fm-clog", "leads_to", "fm-level", 2) in pairs
    assert ("k-osc", "explains", "fm-level", 1) in pairs
    # The link's history shows on the box it starts from.
    assert any(
        "Changed link" in h["summary"] for h in stl_editor.get("/api/boxes/fm-clog/history").json()
    )
    with sample_database.session() as s:
        assert_revisions_match_rows(s)


# ---------------------------------------------------------------- the control plan (M17)

# Every failure mode that leads to a defect, and the boxes above it.
CAUSES_AND_ABOVE = {
    "cc",
    "tun",
    "tun-flow",
    "fm-clog",
    "tun-slag",
    "fm-slag",
    "mould",
    "m-level",
    "fm-level",
    "m-powder",
    "fm-powder",
    "m-osc",
    "fm-osc",
    "sec",
    "sec-spray",
    "fm-spray",
    "bow",
    "bow-unb",
    "fm-duct",
    "cut",
    "cut-torch",
    "fm-burr",
}


def test_the_control_plan_of_a_department(board: TestClient) -> None:
    plan = board.get("/api/control-plan", params={"department": "stl"}).json()
    assert plan["department"]["code"] == "STL"
    defects = [b["key"] for b in plan["boxes"] if b["process_id"] is None]
    assert defects == [
        "d-sliver",
        "d-blisters",
        "d-incl",
        "d-trans",
        "d-long",
        "d-corner",
        "d-edge",
    ]
    causes: dict[str, set[str]] = {}
    for link in plan["links"]:
        assert link["type"] == "leads_to"
        causes.setdefault(link["to_key"], set()).add(link["from_key"])
    assert causes["d-sliver"] == {"fm-clog", "fm-slag", "fm-level", "fm-powder"}
    assert causes["d-blisters"] == {"fm-powder"} and causes["d-trans"] == {"fm-osc", "fm-duct"}
    # Only what leads to a defect, with the boxes above it (not "Caster overview").
    in_maps = {b["key"]: b["parent_key"] for b in plan["boxes"] if b["process_id"] is not None}
    assert in_maps == {key: CC_TREE[key] for key in CAUSES_AND_ABOVE}
    assert {c["box_key"] for c in plan["controls"]} == {
        "fm-level",
        "fm-powder",
        "fm-clog",
        "fm-slag",
    }
    level = [c for c in plan["controls"] if c["box_key"] == "fm-level"]
    assert [len(c["external_links"]) for c in level] == [1, 1, 1]
    assert plan["defect_sections"] == []  # anonymous visitors only read


def test_who_may_read_the_control_plan(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    assert board.get("/api/control-plan", params={"department": "XX"}).status_code == 404
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get("/api/control-plan", params={"department": "STL"}).status_code == 401
    # The Quality section owns the defects, the Process section the maps: no causes then.
    login_as("quality", roles=[(BuiltinRole.VIEWER, Scope.section(ids.sections["Quality"]))])
    plan = board.get("/api/control-plan", params={"department": "STL"}).json()
    assert len(plan["boxes"]) == 7 and plan["links"] == [] and plan["controls"] == []
    login_as("coatings", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Coatings"]))])
    assert board.get("/api/control-plan", params={"department": "STL"}).status_code == 404
    login_as("stl", roles=[(BuiltinRole.EDITOR, Scope.department(ids.departments["STL"]))])
    plan = board.get("/api/control-plan", params={"department": "STL"}).json()
    stl = {ids.sections[name] for name in ("Quality", "Process", "Maintenance")}
    assert set(plan["defect_sections"]) == stl
