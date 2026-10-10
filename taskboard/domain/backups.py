"""Which backups to keep: the newest few, plus the first of each recent week and month (D-100).

Pure: works on the times the backups were taken, in the server's own time zone (weeks run Monday
to Sunday). Weeks and months count only when they hold a backup, so a scheduled task that stopped
running never makes the last backups expire.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class KeptAs(StrEnum):
    NEWEST = "newest"
    WEEKLY = "weekly"  # the first backup of one of the last weeks that have one
    MONTHLY = "monthly"  # the first backup of one of the last months that have one


@dataclass(frozen=True, slots=True)
class Bounds:
    low: int
    high: int


# At least two newest, one weekly and one monthly backup: a mistaken or misused administrator
# account cannot make the next backup delete every earlier one.
LIMITS: dict[KeptAs, Bounds] = {
    KeptAs.NEWEST: Bounds(2, 30),
    KeptAs.WEEKLY: Bounds(1, 26),
    KeptAs.MONTHLY: Bounds(1, 24),
}


@dataclass(frozen=True, slots=True)
class Retention:
    newest: int = 2
    weekly: int = 1
    monthly: int = 2


def _firsts(newest_first: list[datetime], period: str, count: int) -> list[datetime]:
    """The earliest backup of each of the `count` most recent periods that hold one."""
    first_in: dict[tuple[int, int], datetime] = {}  # insertion order: most recent period first
    for taken in newest_first:
        key = taken.isocalendar()[:2] if period == "week" else (taken.year, taken.month)
        first_in[key] = taken  # an earlier backup of the same period replaces a later one
    return list(first_in.values())[:count]


def kept_backups(taken: Iterable[datetime], retention: Retention) -> dict[datetime, list[KeptAs]]:
    """The backups to keep, each with why; every other backup may be deleted."""
    newest_first = sorted(set(taken), reverse=True)
    kept: dict[datetime, list[KeptAs]] = {}
    for kind, chosen in (
        (KeptAs.NEWEST, newest_first[: retention.newest]),
        (KeptAs.WEEKLY, _firsts(newest_first, "week", retention.weekly)),
        (KeptAs.MONTHLY, _firsts(newest_first, "month", retention.monthly)),
    ):
        for moment in chosen:
            kept.setdefault(moment, []).append(kind)
    return kept
