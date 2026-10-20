"""Recent activity rules (milestone M25): which kind a post is, page cursors, and excerpts."""

import re
from datetime import UTC, datetime

import pytest

from taskboard.domain.activity import (
    CURSOR_PATTERN,
    EXCERPT_LENGTH,
    Cursor,
    PostKind,
    excerpt,
    post_kind,
)


def test_post_kinds() -> None:
    assert post_kind(is_update=False, is_period=False) == PostKind.COMMENT
    assert post_kind(is_update=True, is_period=False) == PostKind.UPDATE
    assert post_kind(is_update=False, is_period=True) == PostKind.PERIOD


@pytest.mark.parametrize(
    "at",
    [
        datetime(2026, 10, 2, 9, 10, tzinfo=UTC),
        datetime(2026, 10, 2, 9, 10, 0, 123456, tzinfo=UTC),  # microseconds survive
        datetime(1970, 1, 1, tzinfo=UTC),
    ],
)
def test_cursors_round_trip(at: datetime) -> None:
    text = Cursor(at, 42).encode()
    assert re.fullmatch(CURSOR_PATTERN, text)
    assert Cursor.decode(text) == Cursor(at, 42)


def test_cursors_are_digits_only_so_they_need_no_escaping_in_a_url() -> None:
    assert Cursor(datetime(2026, 10, 2, 9, 10, tzinfo=UTC), 7).encode() == "1790932200000000-7"


@pytest.mark.parametrize("text", ["", "12", "-3", "12-", "a-1", "1.5-2", "9999999999999999999-1"])
def test_anything_else_is_not_a_cursor(text: str) -> None:
    with pytest.raises(ValueError, match="not a cursor"):
        Cursor.decode(text)


def test_excerpts_are_one_line_of_plain_text() -> None:
    markdown = "**Week 40 status**\n\n- All panels pass\n- See [the report](https://x/r.pdf) `R-1`"
    assert excerpt(markdown) == "Week 40 status · All panels pass · See the report R-1"
    assert excerpt("Short.") == "Short."
    assert excerpt("") == ""


def test_blocks_are_set_apart_unless_a_sentence_ends_them() -> None:
    assert excerpt("Proposed date: 12 Nov.\n\nPlease keep it free") == (
        "Proposed date: 12 Nov. Please keep it free"
    )
    assert excerpt("A sentence that\nwraps over lines") == "A sentence that wraps over lines"
    assert excerpt("## Plan\nFirst step\n1. One\n2) Two") == "Plan · First step · One · Two"
    assert excerpt("Steps:\n* one\n+ two") == "Steps: one · two"


def test_long_posts_are_cut_at_a_word() -> None:
    words = "lorem ipsum dolor sit amet " * 20
    cut = excerpt(words)
    assert cut.endswith("…") and len(cut) <= EXCERPT_LENGTH + 1
    assert words.startswith(cut[:-1]) and words[len(cut) - 1] == " "
    assert excerpt("x" * 300, length=50) == "x" * 50 + "…"  # one long word: cut anyway
