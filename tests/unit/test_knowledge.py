"""Process knowledge rules: box keys, extra fields, facts, external links, order, revision diffs."""

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from taskboard.domain.errors import RuleViolationError
from taskboard.domain.knowledge import (
    BUILTIN_KINDS,
    BUILTIN_LINK_TYPES,
    BoxRole,
    LinkRole,
    changed_fields,
    check_facts,
    check_field_schema,
    check_fields,
    check_url,
    slugify,
    stable_positions,
    unique_key,
    with_box_param,
)


def test_box_keys_are_readable_slugs() -> None:
    assert slugify("Mould level fluctuation") == "mould-level-fluctuation"
    assert slugify("Ladle preheating +50 °C") == "ladle-preheating-50-c"
    assert slugify("Chloé's  «test»") == "chloe-s-test"
    assert slugify("!!!") == "box"
    assert len(slugify("x" * 200)) == 60


def test_box_keys_are_unique_and_never_too_long() -> None:
    assert unique_key("Mould", []) == "mould"
    assert unique_key("Mould", ["mould"]) == "mould-2"
    assert unique_key("Mould", ["mould", "mould-2"]) == "mould-3"
    long = "y" * 80
    first = slugify(long)
    key = unique_key(long, [first])
    assert key.endswith("-2") and len(key) <= 60


def test_the_built_in_kinds_and_link_types_of_the_design() -> None:
    assert [k.key for k in BUILTIN_KINDS] == ["step", "know", "ref", "rule", "fm", "defect"]
    assert {k.key: k.role for k in BUILTIN_KINDS}["fm"] is BoxRole.FAILURE_MODE
    leads_to = next(t for t in BUILTIN_LINK_TYPES if t.role is LinkRole.LEADS_TO)
    assert (leads_to.forward_name, leads_to.backward_name) == ("leads to", "caused by")


def test_extra_fields_follow_their_schema() -> None:
    schema = check_field_schema(
        [{"key": "group", "label": "Group"}, {"key": "severity", "type": "number"}]
    )
    assert schema == [
        {"key": "group", "label": "Group", "type": "text"},
        {"key": "severity", "label": "severity", "type": "number"},
    ]
    assert check_fields({"group": "Surface", "severity": 8}, schema) == {
        "group": "Surface",
        "severity": 8,
    }
    assert check_fields({"group": "", "severity": None}, schema) == {}
    with pytest.raises(RuleViolationError, match="no such field"):
        check_fields({"grup": "Surface"}, schema)
    with pytest.raises(RuleViolationError, match="is a number"):
        check_fields({"severity": "high"}, schema)
    with pytest.raises(RuleViolationError, match="twice"):
        check_field_schema([{"key": "a"}, {"key": "a"}])
    with pytest.raises(RuleViolationError, match="lowercase"):
        check_field_schema([{"key": "Severity"}])


def test_key_facts_are_an_ordered_table() -> None:
    facts = check_facts([("Strands", " 2 "), ("", "dropped"), ("Slab width", "[MIN]–[MAX] mm")])
    assert facts == [["Strands", "2"], ["Slab width", "[MIN]–[MAX] mm"]]


def test_external_links_are_web_addresses_only() -> None:
    assert (
        check_url(" https://grafana.plant.local/d/mould ") == "https://grafana.plant.local/d/mould"
    )
    assert check_url("") is None
    for bad in ("javascript:alert(1)", "file:///etc/passwd", "grafana.plant.local", "ftp://x"):
        with pytest.raises(RuleViolationError):
            check_url(bad)


def test_a_dashboard_can_receive_the_box_key() -> None:
    assert (
        with_box_param("https://g.local/d/mould", "fm-level")
        == "https://g.local/d/mould?node=fm-level"
    )
    assert (
        with_box_param("https://g.local/d?x=1", "fm-level") == "https://g.local/d?x=1&node=fm-level"
    )


def test_what_changed_between_revisions() -> None:
    before = {"name": "A", "body_md": "x", "facts": []}
    after = {"name": "A", "body_md": "y", "facts": [["k", "v"]]}
    assert changed_fields(before, after) == ["body_md", "facts"]
    assert changed_fields(None, after) == []


# ---------------------------------------------------------------- order


def test_appending_and_inserting_change_only_the_new_item() -> None:
    assert stable_positions([1024, 2048, None]) == [1024, 2048, 3072]
    assert stable_positions([1024, None, 2048]) == [1024, 1536, 2048]
    assert stable_positions([None, 1024]) == [512, 1024]
    assert stable_positions([None, None]) == [1024, 2048]


def test_moving_an_item_changes_only_that_item() -> None:
    # The third of four moves to the front: the others keep their positions.
    assert stable_positions([3072, 1024, 2048, 4096]) == [512, 1024, 2048, 4096]


def test_when_there_is_no_room_everything_is_renumbered() -> None:
    assert stable_positions([1, None, 2]) == [1024, 2048, 3072]


@given(st.lists(st.one_of(st.none(), st.integers(min_value=0, max_value=10_000)), max_size=12))
def test_positions_always_follow_the_wanted_order(current: list[int | None]) -> None:
    positions = stable_positions(current)
    assert len(positions) == len(current)
    assert all(a < b for a, b in itertools.pairwise(positions))


@given(st.lists(st.integers(min_value=0, max_value=10_000), unique=True, min_size=1, max_size=12))
def test_items_already_in_order_keep_their_positions(current: list[int]) -> None:
    ordered = sorted(current)
    assert stable_positions(ordered) == ordered
