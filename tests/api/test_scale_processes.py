"""2,000 process changes and a 2,000-box map (milestone M20): the API stays fast.

Measured on a laptop: the map ~0.5 s, the draft and a release ~0.25 s, a change list ~0.25 s,
search ~0.1 s. The limits are several times that, so they catch regressions such as a query per
object, not slow machines. Every statement also stays within MS SQL's 2,100 parameters
(tests/conftest.py).
"""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taskboard.db.session import Database
from tests.api.conftest import LoginAs
from tests.scale import add_changes, add_map

CHANGES = 2000
BOXES = 2000


@pytest.fixture
def admin(sample_database: Database, login_as: LoginAs) -> TestClient:
    with sample_database.session(write=True) as s:
        add_changes(s, "LM", CHANGES)
        add_map(s, "CC", BOXES)
    return login_as("admin")


def timed(client: TestClient, method: str, url: str, limit: float, **kwargs: Any) -> Any:
    start = time.perf_counter()
    response = client.request(method, url, **kwargs)
    elapsed = time.perf_counter() - start
    assert response.status_code in (200, 201), response.text
    assert elapsed < limit, f"{method} {url} took {elapsed:.2f}s (limit {limit}s)"
    return response.json()


def test_process_changes_and_search(admin: TestClient) -> None:
    listed = timed(admin, "GET", "/api/changes", limit=2.0, params={"process": "LM"})
    assert len(listed) >= CHANGES
    found = timed(admin, "GET", "/api/search", limit=1.0, params={"q": "generated cooling"})
    groups = {g["type"]: g for g in found["groups"]}
    assert groups["changes"]["total"] > 100 and groups["knowledge"]["total"] > 100
    assert len(groups["changes"]["hits"]) == 20


def test_the_map_its_documents_and_a_release(admin: TestClient) -> None:
    graph = timed(admin, "GET", "/api/processes/CC/map", limit=3.0)
    assert len(graph["boxes"]) > BOXES
    timed(admin, "GET", "/api/control-plan", limit=2.0, params={"department": "STL"})
    releases = timed(admin, "GET", "/api/processes/CC/releases", limit=2.0)
    assert len(releases["draft"]["entries"]) > 600  # every generated failure mode is new
    timed(admin, "POST", "/api/processes/CC/releases", limit=2.0, json={"note": "", "base": 3})
    timed(admin, "GET", "/api/processes/CC/map", limit=2.0, params={"release": 4})
    plan = {"department": "STL", "process": "CC", "release": 4}
    timed(admin, "GET", "/api/control-plan", limit=2.0, params=plan)


def test_editing_and_moving_in_a_big_map(admin: TestClient) -> None:
    saved = admin.get("/api/boxes/gen-step-3-2").json()
    box = saved["box"]
    body = {k: box[k] for k in ("version", "kind", "name", "main_url", "facts", "fields")}
    body |= {"body_md": "Edited.", "step_no": None, "owner_person_id": None}
    body |= {"external_links": [], "links": [], "controls": []}
    timed(admin, "PATCH", "/api/boxes/gen-step-3-2", limit=1.5, json=body)
    move = {"parent_key": "gen-zone-7", "before_key": "gen-step-7-0"}
    timed(admin, "POST", "/api/boxes/gen-step-3-2/move", limit=1.5, json=move)
    timed(admin, "GET", "/api/boxes/gen-zone-7/history", limit=1.5)
    timed(admin, "GET", "/api/boxes/gen-zone-7/related", limit=1.5)
