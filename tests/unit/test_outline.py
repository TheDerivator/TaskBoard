"""Project outlines: numbering, order, subtrees, counts including descendants, cycle checks."""

import json
from pathlib import Path

import pytest

from taskboard.domain.outline import Outline, TreeNode, subtree_counts

SAMPLE = json.loads(
    (Path(__file__).resolve().parents[2] / "team-tasks-design" / "sample-data.json").read_text(
        encoding="utf-8"
    )
)


def outline_of(project: str) -> Outline[str]:
    return Outline(
        TreeNode(n["id"], n["parent_id"], n["position"])
        for n in SAMPLE["project_nodes"]
        if n["project_id"] == project
    )


@pytest.mark.parametrize("project", ["ASQ", "P26", "SAF"])
def test_numbers_match_the_sample_data(project: str) -> None:
    outline = outline_of(project)
    for node in SAMPLE["project_nodes"]:
        if node["project_id"] == project:
            assert outline.number(node["id"]) == node["number"]


def test_preorder_is_outline_order() -> None:
    numbers = [outline_of("ASQ").number(n) for n in outline_of("ASQ").preorder()]
    assert numbers == ["1", "1.1", "1.2", "2", "2.1", "2.2", "2.2.1", "3"]


def test_numbers_follow_positions_not_insertion_order_and_tolerate_gaps() -> None:
    outline = Outline([TreeNode("b", None, 20), TreeNode("a", None, 10), TreeNode("c", "b", 5)])
    assert [outline.number(n) for n in ("a", "b", "c")] == ["1", "2", "2.1"]


def test_depth_ancestors_and_subtree() -> None:
    outline = outline_of("ASQ")
    assert outline.depth("ASQ:2.2.1") == 3
    assert outline.ancestors("ASQ:2.2.1") == ["ASQ:2", "ASQ:2.2"]
    assert outline.subtree("ASQ:2") == {"ASQ:2", "ASQ:2.1", "ASQ:2.2", "ASQ:2.2.1"}
    assert outline.children(None) == ["ASQ:1", "ASQ:2", "ASQ:3"]


def test_counts_include_descendants() -> None:
    """ASQ in the sample: T-075 on 2, T-104 on 2.1, T-098 on 2.2.1 → node 2 counts 3."""
    outline = outline_of("ASQ")
    direct = {"ASQ:2": 1, "ASQ:2.1": 1, "ASQ:2.2.1": 1, "ASQ:3": 2}
    totals = subtree_counts(outline, direct)
    assert totals["ASQ:2"] == 3
    assert totals["ASQ:2.2"] == 1
    assert totals["ASQ:1"] == 0
    assert totals["ASQ:3"] == 2


def test_cycle_detection() -> None:
    outline = outline_of("ASQ")
    assert outline.would_create_cycle("ASQ:2", "ASQ:2.2.1")
    assert outline.would_create_cycle("ASQ:2", "ASQ:2")
    assert not outline.would_create_cycle("ASQ:2.2", "ASQ:1")
    assert not outline.would_create_cycle("ASQ:2.2", None)
