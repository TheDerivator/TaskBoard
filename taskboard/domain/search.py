"""Search everything (DESIGN "Global search", M19): the words of a query, whether a text holds
them (ignoring case across all of Unicode: "é" finds "É"), how well a title matches, and a short
plain-text snippet around the first match for the result's context line."""

import re
from collections.abc import Iterable, Sequence

MIN_QUERY_LENGTH = 2  # one letter would match nearly everything
MAX_WORDS = 8


def words_of(query: str) -> list[str]:
    """The query's words, case-folded, each once, in order: every one must match somewhere."""
    words: list[str] = []
    for word in query.casefold().split():
        if word not in words:
            words.append(word)
    return words[:MAX_WORDS]


def searchable(query: str) -> bool:
    return len(query.strip()) >= MIN_QUERY_LENGTH and bool(words_of(query))


def holds(text: str | None, word: str) -> bool:
    return bool(text) and word in text.casefold()  # type: ignore[union-attr]


def holds_all(texts: Iterable[str | None], words: Sequence[str]) -> bool:
    """Every word is in one of the texts (not necessarily the same one)."""
    folded = " \n".join(t.casefold() for t in texts if t)
    return all(word in folded for word in words)


def title_score(title: str, words: Sequence[str]) -> int:
    """3: the whole query as written is in the title; 2: all its words are; 1: some are; 0: none.
    Results are ranked by this first (DESIGN: grouped, ranked)."""
    folded = title.casefold()
    if " ".join(words) in folded:
        return 3
    found = sum(word in folded for word in words)
    if found == len(words):
        return 2
    return 1 if found else 0


_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MARKS = re.compile(r"[*_`#>~|]+")
_SPACE = re.compile(r"\s+")


def plain(markdown: str) -> str:
    """Markdown as one line of plain text: links keep their text, marks and line breaks go."""
    return _SPACE.sub(" ", _MARKS.sub("", _LINK.sub(r"\1", markdown))).strip()


def snippet(text: str, words: Sequence[str], width: int = 90) -> str | None:
    """About `width` characters of `text` around the first match of the query (as written, else
    its earliest word), with "…" where text was cut; None when the text holds none of it."""
    # Case folding may change lengths ("ß" → "ss"): map folded positions back to the text's.
    origin: list[int] = []
    for i, char in enumerate(text):
        origin.extend([i] * len(char.casefold()))
    folded = text.casefold()
    phrase = " ".join(words)
    found = folded.find(phrase) if phrase else -1
    if found < 0:
        hits = [i for i in (folded.find(w) for w in words if w) if i >= 0]
        if not hits:
            return None
        found = min(hits)
    at = origin[found]
    start = max(0, at - width // 3)
    if start > 0:  # start at a word
        space = text.find(" ", start)
        start = space + 1 if 0 <= space < at else start
    end = min(len(text), start + width)
    if end < len(text):
        space = text.rfind(" ", at, end)
        end = space if space > at else end
    return f"{'…' if start > 0 else ''}{text[start:end].strip()}{'…' if end < len(text) else ''}"
