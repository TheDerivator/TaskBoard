"""Short task keys: alphabet, length, forgiving input, display, collision retry."""

import itertools
import re

import pytest

from taskboard.domain.errors import ConflictError
from taskboard.domain.task_keys import (
    ALPHABET,
    KEY_LENGTH,
    InvalidTaskKeyError,
    display_key,
    generate_key,
    generate_unique_key,
    normalize_key,
)


def test_alphabet_is_crockford_base32() -> None:
    assert len(ALPHABET) == len(set(ALPHABET)) == 32
    assert not set("ILOU") & set(ALPHABET)


def test_generated_keys_have_fixed_length_and_valid_characters() -> None:
    for _ in range(200):
        key = generate_key()
        assert re.fullmatch(f"[{ALPHABET}]{{{KEY_LENGTH}}}", key)


def test_generated_keys_are_random() -> None:
    assert len({generate_key() for _ in range(1000)}) == 1000


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("K7Q2MX", "K7Q2MX"),
        ("t-k7q2mx", "K7Q2MX"),
        ("  T-K7Q2MX ", "K7Q2MX"),
        ("k7q2mo", "K7Q2M0"),
        ("il0", "110"),
        ("T-104", "104"),
    ],
)
def test_normalize_is_forgiving(text: str, expected: str) -> None:
    assert normalize_key(text) == expected


@pytest.mark.parametrize("text", ["", "T-", "K7Q2MU", "K7-Q2", "ÄBC", "X" * 17])
def test_normalize_rejects_garbage(text: str) -> None:
    with pytest.raises(InvalidTaskKeyError):
        normalize_key(text)


def test_display_key() -> None:
    assert display_key("K7Q2MX") == "T-K7Q2MX"


def test_unique_key_retries_on_collision() -> None:
    taken = {"000000", "111111"}
    chars = itertools.chain("000000", "111111", "222222")
    key = generate_unique_key(taken.__contains__, choice=lambda _: next(chars))
    assert key == "222222"


def test_unique_key_gives_up_eventually() -> None:
    with pytest.raises(ConflictError):
        generate_unique_key(lambda _: True, attempts=3)
