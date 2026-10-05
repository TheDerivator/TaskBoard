"""Process changes: keys (`LM-07`), period rules, scope tags, and the derived state of a change.

DESIGN Module 2: a change's periods are posted in its conversation. A *test* has an end date
(inclusive); a *process change* has none when posted, and may get one later when it is ended
(reverted). The state ("In effect", "Test running", ...) is derived from the periods and today's
date, never stored. The same rules exist in the browser (`static/js/lib/periods.js`); both are
tested against `tests/fixtures/change_states.json`.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from taskboard.domain.errors import RuleViolationError

MAX_LABEL_LENGTH = 100
MAX_TAG_LENGTH = 80
MAX_TAGS = 20


class PeriodKind(StrEnum):
    TEST = "test"  # has an end date
    CHANGE = "change"  # a permanent process change: no end date, until it is ended

    @property
    def default_label(self) -> str:
        return "Test" if self is PeriodKind.TEST else "Process change"


class ChangeState(StrEnum):
    IN_EFFECT = "in_effect"  # a process change has started and has not ended
    TEST_RUNNING = "test_running"  # a test includes today
    PLANNED = "planned"  # a period starts after today
    NO_PERIODS = "no_periods"
    TESTS_ENDED = "tests_ended"  # everything is over; the last period was a test
    ENDED = "ended"  # everything is over; the last period was a process change (reverted)


@dataclass(frozen=True, slots=True)
class Period:
    kind: PeriodKind
    start: date
    end: date | None


@dataclass(frozen=True, slots=True)
class StateOn:
    """A change's state on a given day, and the date its wording mentions ("since 21 Apr")."""

    state: ChangeState
    date: date | None


def change_state(periods: Iterable[Period], today: date) -> StateOn:
    """The first rule that matches wins (the order of the ChangesList mockup)."""
    periods = list(periods)
    in_effect = [
        p.start
        for p in periods
        if p.kind is PeriodKind.CHANGE and p.start <= today and (p.end is None or p.end >= today)
    ]
    if in_effect:
        return StateOn(ChangeState.IN_EFFECT, min(in_effect))
    running = [
        p.end
        for p in periods
        if p.kind is PeriodKind.TEST and p.end is not None and p.start <= today <= p.end
    ]
    if running:
        return StateOn(ChangeState.TEST_RUNNING, max(running))
    planned = [p.start for p in periods if p.start > today]
    if planned:
        return StateOn(ChangeState.PLANNED, min(planned))
    if not periods:
        return StateOn(ChangeState.NO_PERIODS, None)
    # Everything is over, so every period has an end date before today.
    last = max(periods, key=lambda p: (p.end or p.start, p.kind is PeriodKind.CHANGE))
    ended = ChangeState.ENDED if last.kind is PeriodKind.CHANGE else ChangeState.TESTS_ENDED
    return StateOn(ended, last.end)


def check_period(kind: PeriodKind, start: date, end: date | None) -> None:
    """A test needs an end date; no period ends before it starts (end dates are inclusive)."""
    if kind is PeriodKind.TEST and end is None:
        raise RuleViolationError("a test needs an end date (without one it is a process change)")
    if end is not None and end < start:
        raise RuleViolationError("the end date is before the start date")


def period_label(kind: PeriodKind, label: str | None) -> str:
    text = " ".join((label or "").split())[:MAX_LABEL_LENGTH]
    return text or kind.default_label


def normalize_tags(tags: Sequence[str]) -> list[str]:
    """Scope tags are free text (DESIGN rule 4): tidy spaces, drop empty ones and repeats
    (ignoring case, the first spelling stays)."""
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = " ".join(tag.split())[:MAX_TAG_LENGTH]
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            result.append(text)
    if len(result) > MAX_TAGS:
        raise RuleViolationError(f"a period can have at most {MAX_TAGS} scope tags")
    return result


# ---------------------------------------------------------------- keys


def change_key(process_code: str, number: int) -> str:
    """`LM`, 7 → `LM-07`. The key is fixed: it stays when the change moves to another process."""
    return f"{process_code}-{number:02d}"


def normalize_change_key(text: str) -> str:
    """Links are forgiving about case: `lm-07` → `LM-07`."""
    return text.strip().upper()
