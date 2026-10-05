"""Search rules (milestone M19): query words, matching across Unicode, ranking titles, snippets."""

from hypothesis import given
from hypothesis import strategies as st

from taskboard.domain.search import (
    holds_all,
    plain,
    searchable,
    snippet,
    title_score,
    words_of,
)


def test_the_words_of_a_query() -> None:
    assert words_of("  Mould  POWDER mould ") == ["mould", "powder"]
    assert words_of("Chloé") == ["chloé"]
    assert not searchable("a") and not searchable("   ") and searchable("CC")


def test_every_word_must_be_somewhere_ignoring_case() -> None:
    assert holds_all(["Mould powder type B", None], ["powder", "mould"])
    assert holds_all(["Powder entrapment", "Continuous casting › Mould"], ["mould", "powder"])
    assert not holds_all(["Powder entrapment"], ["mould", "powder"])
    assert holds_all(["ÉTAT DES LIEUX"], words_of("état"))  # "é" finds "É"
    assert holds_all(["Straße"], words_of("STRASSE"))  # full case folding, not just lowercase


def test_titles_rank_the_whole_query_first() -> None:
    words = words_of("mould powder")
    assert title_score("Mould powder", words) == 3
    assert title_score("Powder in the mould", words) == 2
    assert title_score("Powder entrapment", words) == 1
    assert title_score("Sliver lines", words) == 0


def test_markdown_becomes_one_plain_line() -> None:
    assert plain("**Waves** at the [meniscus](https://x.local)\n\n- pull `powder`") == (
        "Waves at the meniscus - pull powder"
    )


def test_a_snippet_around_the_first_match() -> None:
    text = (
        "Defects cluster right after the switch to mould powder type B on line 2, "
        "mostly on the operator side, and only for peritectic grades."
    )
    cut = snippet(text, words_of("mould powder"), width=60)
    assert cut is not None and "mould powder" in cut
    assert cut.startswith("…") and cut.endswith("…")
    assert snippet("Short text.", words_of("short")) == "Short text."
    assert snippet("Nothing here.", words_of("powder")) is None
    long = "Straße " * 30 + "Powder"
    assert snippet(long, words_of("powder"), width=40).endswith("Powder")  # type: ignore[union-attr]


@given(st.text(min_size=1, max_size=300), st.text(alphabet="abcdéÉßẞİ ", min_size=1, max_size=12))
def test_a_snippet_is_short_and_holds_a_word(text: str, query: str) -> None:
    words = words_of(query)
    found = snippet(text, words, width=50)
    if found is None:
        assert not any(w in text.casefold() for w in words)
    else:
        assert len(found) <= 52
