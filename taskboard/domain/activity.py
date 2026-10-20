"""Recent activity (M25, D-104): what is listed, which posts count, where a page ends, excerpts.

Tasks and process changes are listed by their newest post: comments, status updates and periods.
Automatic events and edits of older posts do not count, so a typo fix never moves a task up.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Self

from taskboard.domain.search import plain

DEFAULT_PAGE = 30
MAX_PAGE = 100
EXCERPT_LENGTH = 200
CURSOR_PATTERN = r"^\d{1,19}-\d{1,19}$"  # "<microseconds since 1970>-<post id>"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSECOND = timedelta(microseconds=1)


class ActivityType(StrEnum):
    TASK = "task"
    CHANGE = "change"  # a process change


class PostKind(StrEnum):
    COMMENT = "comment"
    UPDATE = "update"  # a task's status update
    PERIOD = "period"  # a process change's test or permanent change


def post_kind(*, is_update: bool, is_period: bool) -> PostKind:
    if is_period:
        return PostKind.PERIOD
    return PostKind.UPDATE if is_update else PostKind.COMMENT


@dataclass(frozen=True, slots=True)
class Cursor:
    """Where a page ended: the newest post of its last item. The next page lists what is older,
    so an item that gets a new post meanwhile moves to the top instead of showing up twice."""

    at: datetime  # timezone-aware
    post_id: int

    def encode(self) -> str:
        return f"{(self.at - _EPOCH) // _MICROSECOND}-{self.post_id}"

    @classmethod
    def decode(cls, text: str) -> Self:
        """The cursor written by `encode`; ValueError for anything else."""
        micros, dash, post_id = text.partition("-")
        if not (dash and micros.isdigit() and post_id.isdigit()):
            raise ValueError(f"not a cursor: {text!r}")
        try:
            at = _EPOCH + int(micros) * _MICROSECOND
        except OverflowError as error:
            raise ValueError(f"not a cursor: {text!r}") from error
        return cls(at, int(post_id))


_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#")
_SENTENCE_END = (".", "!", "?", ":", ";", ",", "…")


def _blocks(markdown: str) -> list[str]:
    """Paragraphs, headings and list items, each as one line of plain text."""
    blocks: list[list[str]] = [[]]
    for line in markdown.splitlines():
        if not line.strip() or _LIST_ITEM.match(line) or _HEADING.match(line):
            blocks.append([])
        if line.strip():
            blocks[-1].append(_LIST_ITEM.sub("", line))
            if _HEADING.match(line):
                blocks.append([])
    return [text for text in (plain(" ".join(b)) for b in blocks) if text]


def excerpt(markdown: str, length: int = EXCERPT_LENGTH) -> str:
    """A post as one line of plain text, cut at a word after about `length` characters ("…").
    A heading, list item or paragraph that ends without a full stop gets a " · " after it."""
    text = ""
    for block in _blocks(markdown):
        joint = " " if not text or text.endswith(_SENTENCE_END) else " · "
        text = f"{text}{joint}{block}".strip()
    if len(text) <= length:
        return text
    space = text.rfind(" ", 0, length + 1)
    cut = space if space > length // 2 else length
    return text[:cut].rstrip() + "…"
