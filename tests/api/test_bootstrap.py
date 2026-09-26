"""The bootstrap document and the people list, for visitors with and without access."""

from fastapi.testclient import TestClient

from taskboard.db.session import Database
from tests.helpers import revoke_anonymous_access


def test_bootstrap_for_a_visitor(board: TestClient) -> None:
    body = board.get("/api/bootstrap").json()
    assert body["me"]["is_anonymous"] is True
    assert [(d["code"], [s["name"] for s in d["sections"]]) for d in body["departments"]] == [
        ("STL", ["Quality", "Process", "Maintenance"]),
        ("R&D", ["Coatings"]),
    ]
    assert [p["code"] for p in body["people"]] == ["AC", "BP", "CM", "DW", "EJ", "FM"]
    assert [p["key"] for p in body["projects"]] == ["ASQ", "P26", "SAF"]
    assert [(s["value"], s["shown_by_default"]) for s in body["statuses"]] == [
        ("idea", True),
        ("started", True),
        ("done", True),
        ("archived", False),
    ]
    assert body["task_total"] == 11


def test_bootstrap_when_the_board_is_login_only(
    board: TestClient, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    body = board.get("/api/bootstrap").json()
    assert body["me"]["is_anonymous"] is True
    assert body["people"] == [] and body["projects"] == [] and body["task_total"] == 0
    assert board.get("/api/people").status_code == 401
