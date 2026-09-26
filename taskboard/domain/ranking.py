"""The team-wide ranking: moving a task before/after another one, as list and as rank shift.

Ranks are dense `1..N` over all tasks. Moving one task only changes the ranks between its old
and new position, which `plan_move` expresses as a single range shift so the database can apply
it with one UPDATE. Filters never change ranks (DESIGN rule 2): a drop in a filtered list is a
move relative to the row it was dropped on, which is exactly what these functions take.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from taskboard.domain.errors import RuleViolationError


class Where(StrEnum):
    BEFORE = "before"
    AFTER = "after"


def drop_side(order: Sequence[object], dragged: object, target: object) -> Where:
    """Which side of `target` a dragged item lands on (from the mockup): moving down → after."""
    return Where.AFTER if order.index(dragged) < order.index(target) else Where.BEFORE


def move[T](order: Sequence[T], item: T, target: T, where: Where) -> list[T]:
    """Return `order` with `item` placed directly before or after `target`."""
    if item == target:
        return list(order)
    result = [x for x in order if x != item]
    index = result.index(target) + (1 if where is Where.AFTER else 0)
    result.insert(index, item)
    return result


@dataclass(frozen=True, slots=True)
class RankShift:
    """Result of planning a move: the item's new rank, plus `delta` for every rank in [lo, hi]."""

    new_rank: int
    lo: int
    hi: int
    delta: int

    @property
    def is_noop(self) -> bool:
        return self.lo > self.hi


def plan_move(current_rank: int, target_rank: int, where: Where, count: int) -> RankShift:
    """Plan moving the task at `current_rank` before/after the one at `target_rank`.

    Apply it as: shift ranks in [lo, hi] by `delta` (excluding the moved task), then give the
    moved task `new_rank`. Ranks are 1-based and dense over `count` tasks.
    """
    if not (1 <= current_rank <= count and 1 <= target_rank <= count):
        raise RuleViolationError("rank out of range")
    if current_rank == target_rank:
        return RankShift(new_rank=current_rank, lo=1, hi=0, delta=0)
    # Position of the target once the moved item is taken out of the list.
    target_after_removal = target_rank - 1 if target_rank > current_rank else target_rank
    new_rank = target_after_removal + (1 if where is Where.AFTER else 0)
    if new_rank > current_rank:
        return RankShift(new_rank=new_rank, lo=current_rank + 1, hi=new_rank, delta=-1)
    if new_rank < current_rank:
        return RankShift(new_rank=new_rank, lo=new_rank, hi=current_rank - 1, delta=+1)
    return RankShift(new_rank=current_rank, lo=1, hi=0, delta=0)


def apply_shift[T](order: Sequence[T], item: T, shift: RankShift) -> list[T]:
    """Apply a RankShift to an ordered list (reference implementation used by the tests)."""
    ranks = {x: i + 1 for i, x in enumerate(order)}
    for x, rank in ranks.items():
        if x != item and shift.lo <= rank <= shift.hi:
            ranks[x] = rank + shift.delta
    ranks[item] = shift.new_rank
    return sorted(order, key=lambda x: ranks[x])
