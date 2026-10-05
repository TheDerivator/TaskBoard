"""Search everything (milestone M19): every type is found, grouped and ranked, with links; nothing
invisible is ever returned; Unicode case is ignored."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from taskboard.db.models import Box, Task
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.api.conftest import Ids, LoginAs
from tests.helpers import revoke_anonymous_access


def _search(client: TestClient, q: str) -> dict[str, dict[str, Any]]:
    response = client.get("/api/search", params={"q": q})
    assert response.status_code == 200, response.text
    return {g["type"]: g for g in response.json()["groups"]}


def _titles(group: dict[str, Any]) -> list[str]:
    return [h["title"] for h in group["hits"]]


def test_mould_powder_finds_the_mockups_groups(board: TestClient) -> None:
    groups = _search(board, "mould powder")
    assert list(groups) == ["knowledge", "changes", "tasks", "defects"]
    knowledge = groups["knowledge"]["hits"]
    assert knowledge[0]["title"] == "Mould powder"  # the whole query in the name comes first
    assert knowledge[0]["context"] == "Process step · Continuous casting › Mould"
    assert knowledge[0]["url"] == "/knowledge/STL/CC/m-powder"
    assert {"Powder entrapment", "Powder datasheets"} <= set(_titles(groups["knowledge"]))
    [change] = groups["changes"]["hits"]
    assert (change["ref"], change["title"]) == ("CC-31", "Mould powder type B")
    assert change["process"] == "Continuous casting" and change["state"] == "in_effect"
    assert change["url"] == "/changes/STL/CC/CC-31"
    [task] = groups["tasks"]["hits"]
    assert task["ref"] == "T-117" and task["url"] == "/t/117"
    assert "Mould powder residues on class A surfaces" in task["context"]
    assert "Sliver lines" in _titles(groups["defects"])
    assert groups["defects"]["hits"][0]["url"].startswith("/cpl/STL/")


def test_each_kind_of_text_is_searched(board: TestClient) -> None:
    found = {h["ref"]: h for h in _search(board, "grinding")["tasks"]["hits"]}
    assert found["T-104"]["context"].startswith("In conversation: “")  # only in its conversation
    assert "Mould level fluctuation" in _titles(_search(board, "meniscus")["knowledge"])  # body
    assert "Caster overview" in _titles(
        _search(board, "metallurgical length")["knowledge"]
    )  # facts
    assert _titles(_search(board, "lm-07")["changes"]) == ["Argon stirring rate during trim"]
    assert "LM-07" in [h["ref"] for h in _search(board, "IF-01")["changes"]["hits"]]  # a tag
    found = _search(board, "T-104")["tasks"]["hits"]
    assert found[0]["ref"] == "T-104"
    assert _search(board, "x")["tasks"]["total"] == 0  # too short to search


def test_unicode_case_is_ignored(board: TestClient, sample_database: Database) -> None:
    with sample_database.session(write=True) as s:
        s.scalars(select(Task).where(Task.key == "104")).one().title = "État des lieux, ligne 2"
        s.scalars(select(Box).where(Box.key == "k-osc")).one().body_md = "Größe der Oszillation"
    assert _titles(_search(board, "état")["tasks"]) == ["État des lieux, ligne 2"]
    assert _titles(_search(board, "ÉTAT")["tasks"]) == ["État des lieux, ligne 2"]
    assert "How oscillation works" in _titles(_search(board, "GRÖSSE")["knowledge"])


def test_nothing_invisible_is_returned(
    board: TestClient, sample_database: Database, login_as: LoginAs, ids: Ids
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
    assert board.get("/api/search", params={"q": "mould"}).status_code == 401
    # Coatings (R&D) sees its own tasks, and none of STL's processes, maps or defects.
    login_as("coatings", roles=[(BuiltinRole.EDITOR, Scope.section(ids.sections["Coatings"]))])
    groups = _search(board, "mould")
    assert all(g["total"] == 0 for g in groups.values())
    assert _search(board, "coating")["tasks"]["total"] >= 1
    # Quality sees the defects (its section) and its tasks, but no Continuous casting map.
    login_as("quality", roles=[(BuiltinRole.VIEWER, Scope.section(ids.sections["Quality"]))])
    groups = _search(board, "mould powder")
    assert groups["knowledge"]["total"] == 0 and groups["changes"]["total"] == 0
    assert "Sliver lines" in _titles(groups["defects"])


@pytest.mark.parametrize("limit", [1, 2])
def test_a_limit_keeps_the_best_but_counts_all(board: TestClient, limit: int) -> None:
    response = board.get("/api/search", params={"q": "mould", "limit": limit}).json()
    knowledge = next(g for g in response["groups"] if g["type"] == "knowledge")
    assert len(knowledge["hits"]) == limit and knowledge["total"] > limit
    assert knowledge["hits"][0]["title"] == "Mould"
