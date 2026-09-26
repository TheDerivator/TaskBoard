"""Short public task keys (`T-K7Q2MX`): generation, normalization and display.

Keys use Crockford's base32 alphabet (digits + letters without I, L, O, U), so they are easy to
read aloud and type. Input is forgiving: case-insensitive, optional `T-` prefix, and the usual
look-alikes (O → 0, I/L → 1) are accepted.
"""

import secrets
from collections.abc import Callable

from taskboard.domain.errors import ConflictError

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
KEY_LENGTH = 6  # 32**6 ≈ 1.07 billion keys
MAX_KEY_LENGTH = 16  # imported keys (e.g. sample data "104") may differ in length
DISPLAY_PREFIX = "T-"

_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


class InvalidTaskKeyError(ValueError):
    """The text cannot be a task key."""


def generate_key(choice: Callable[[str], str] = secrets.choice) -> str:
    """A new random key. `choice` is injectable so tests can be deterministic."""
    return "".join(choice(ALPHABET) for _ in range(KEY_LENGTH))


def generate_unique_key(
    exists: Callable[[str], bool],
    choice: Callable[[str], str] = secrets.choice,
    attempts: int = 20,
) -> str:
    """A random key for which `exists(key)` is false. Collisions are rare; retrying is enough."""
    for _ in range(attempts):
        key = generate_key(choice)
        if not exists(key):
            return key
    raise ConflictError(f"could not find a free task key in {attempts} attempts")


def normalize_key(text: str) -> str:
    """Canonical form of user input: `' t-k7q2mo '` → `'K7Q2M0'`. Raises InvalidTaskKeyError."""
    key = text.strip().upper()
    key = key.removeprefix(DISPLAY_PREFIX)
    key = key.translate(_LOOKALIKES)
    if not 1 <= len(key) <= MAX_KEY_LENGTH or any(c not in ALPHABET for c in key):
        raise InvalidTaskKeyError(f"not a task key: {text!r}")
    return key


def display_key(key: str) -> str:
    """How a key is shown to people: `K7Q2MX` → `T-K7Q2MX`."""
    return f"{DISPLAY_PREFIX}{key}"
