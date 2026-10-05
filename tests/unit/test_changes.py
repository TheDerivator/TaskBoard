"""Process changes: the derived state (the shared table of cases), period rules, tags and keys."""

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from taskboard.domain.changes import (
    ChangeState,
    Period,
    PeriodKind,
    change_key,
    change_state,
    check_period,
    normalize_change_key,
    normalize_tags,
    period_label,
)
from taskboard.domain.errors import RuleViolationError

STATES = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "change_states.json").read_text(encoding="utf-8")
)
TODAY = date.fromisoformat(STATES["today"])


def _period(row: dict[str, Any]) -> Period:
    end = row["end"] and date.fromisoformat(row["end"])
    return Period(PeriodKind(row["kind"]), date.fromisoformat(row["start"]), end)


@pytest.mark.parametrize("case", STATES["cases"], ids=lambda case: case["name"])
def test_the_state_of_a_change(case: dict[str, Any]) -> None:
    """The same table is checked in the browser (tests/js/periods.test.mjs)."""
    result = change_state([_period(p) for p in case["periods"]], TODAY)
    assert result.state == ChangeState(case["state"])
    assert result.date == (case["date"] and date.fromisoformat(case["date"]))


def test_the_state_does_not_depend_on_the_order_of_the_periods() -> None:
    for case in STATES["cases"]:
        periods = [_period(p) for p in case["periods"]]
        assert change_state(reversed(periods), TODAY) == change_state(periods, TODAY)


def test_a_test_needs_an_end_date_and_nothing_ends_before_it_starts() -> None:
    start = date(2026, 10, 12)
    check_period(PeriodKind.TEST, start, start)  # a one-day test
    check_period(PeriodKind.CHANGE, start, None)
    check_period(PeriodKind.CHANGE, start, date(2026, 12, 31))  # ended (reverted) later
    with pytest.raises(RuleViolationError, match="needs an end date"):
        check_period(PeriodKind.TEST, start, None)
    with pytest.raises(RuleViolationError, match="before the start"):
        check_period(PeriodKind.CHANGE, start, date(2026, 10, 11))


def test_labels_default_to_the_kind() -> None:
    assert period_label(PeriodKind.TEST, "  Follow-up   test ") == "Follow-up test"
    assert period_label(PeriodKind.TEST, "") == "Test"
    assert period_label(PeriodKind.CHANGE, None) == "Process change"


def test_scope_tags_are_free_text_without_repeats() -> None:
    tags = ["LF2", " Heats  41230–41236 ", "", "lf2", "All ULC grades"]
    assert normalize_tags(tags) == ["LF2", "Heats 41230–41236", "All ULC grades"]
    with pytest.raises(RuleViolationError, match="at most"):
        normalize_tags([f"tag {n}" for n in range(21)])


def test_change_keys() -> None:
    assert change_key("LM", 7) == "LM-07"
    assert change_key("CC", 131) == "CC-131"
    assert normalize_change_key(" lm-07 ") == "LM-07"
