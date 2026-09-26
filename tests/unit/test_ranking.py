"""Team-wide ranking: moves relative to a target row, and the equivalent database rank shift."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from taskboard.domain.errors import RuleViolationError
from taskboard.domain.ranking import Where, apply_shift, drop_side, move, plan_move

ORDER = ["T-104", "T-117", "T-098", "T-130", "T-089"]


def test_move_down_after_target() -> None:
    assert move(ORDER, "T-117", "T-130", Where.AFTER) == [
        "T-104",
        "T-098",
        "T-130",
        "T-117",
        "T-089",
    ]


def test_move_up_before_target() -> None:
    assert move(ORDER, "T-089", "T-117", Where.BEFORE) == [
        "T-104",
        "T-089",
        "T-117",
        "T-098",
        "T-130",
    ]


def test_move_onto_itself_changes_nothing() -> None:
    assert move(ORDER, "T-098", "T-098", Where.AFTER) == ORDER


def test_drop_side_follows_the_mockup() -> None:
    """Dragging down lands after the target row, dragging up lands before it."""
    assert drop_side(ORDER, "T-104", "T-098") is Where.AFTER
    assert drop_side(ORDER, "T-089", "T-098") is Where.BEFORE


def test_drop_in_a_filtered_list_moves_relative_to_the_drop_row() -> None:
    """Rule 2: only 'started' tasks visible; dropping T-089 on T-117 in that list."""
    visible = ["T-104", "T-117", "T-130", "T-089"]
    side = drop_side(visible, "T-089", "T-117")
    assert move(ORDER, "T-089", "T-117", side) == ["T-104", "T-089", "T-117", "T-098", "T-130"]


def test_plan_move_down() -> None:
    shift = plan_move(current_rank=2, target_rank=4, where=Where.AFTER, count=5)
    assert (shift.new_rank, shift.lo, shift.hi, shift.delta) == (4, 3, 4, -1)


def test_plan_move_up() -> None:
    shift = plan_move(current_rank=5, target_rank=2, where=Where.BEFORE, count=5)
    assert (shift.new_rank, shift.lo, shift.hi, shift.delta) == (2, 2, 4, +1)


@pytest.mark.parametrize(
    ("current", "target", "where"), [(3, 3, Where.AFTER), (3, 4, Where.BEFORE), (3, 2, Where.AFTER)]
)
def test_plan_move_noops(current: int, target: int, where: Where) -> None:
    assert plan_move(current, target, where, count=5).is_noop


def test_plan_move_rejects_ranks_out_of_range() -> None:
    with pytest.raises(RuleViolationError):
        plan_move(current_rank=6, target_rank=1, where=Where.BEFORE, count=5)


@st.composite
def move_cases(draw: st.DrawFn) -> tuple[list[int], int, int, Where]:
    order = draw(st.permutations(list(range(draw(st.integers(min_value=1, max_value=30))))))
    return (
        order,
        draw(st.sampled_from(order)),
        draw(st.sampled_from(order)),
        draw(st.sampled_from(Where)),
    )


@given(move_cases())
def test_move_is_a_permutation_preserving_everyone_elses_order(
    case: tuple[list[int], int, int, Where],
) -> None:
    order, item, target, where = case
    result = move(order, item, target, where)
    assert sorted(result) == sorted(order)
    assert [x for x in result if x != item] == [x for x in order if x != item]
    if item != target:
        offset = 1 if where is Where.AFTER else -1
        assert result.index(item) == result.index(target) + offset


@given(move_cases())
def test_rank_shift_matches_list_move(case: tuple[list[int], int, int, Where]) -> None:
    """The single-UPDATE rank shift the database applies equals the list operation."""
    order, item, target, where = case
    shift = plan_move(order.index(item) + 1, order.index(target) + 1, where, count=len(order))
    assert apply_shift(order, item, shift) == move(order, item, target, where)
