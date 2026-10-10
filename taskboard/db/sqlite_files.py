"""SQLite database files: where they are, consistent copies of them while they are in use, and
whether a copy is sound.

Copies go through SQLite's online backup API, page by page under SQLite's own locking, so a
running app can keep reading and writing. Other backends (MS SQL) are copied with their own
tools; see docs/OPERATIONS.md.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy.engine import make_url


def sqlite_file(url: str) -> Path | None:
    """The file of a SQLite database URL; None for other backends and in-memory databases."""
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or parsed.database in (None, "", ":memory:"):
        return None
    return Path(parsed.database)


def copy_database(source: Path, target: Path) -> None:
    """Make `target` an exact copy of `source` (created if missing, overwritten otherwise)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source)) as from_db,
        closing(sqlite3.connect(target)) as to_db,
    ):
        from_db.backup(to_db)


def database_problems(path: Path) -> list[str]:
    """What SQLite's integrity check finds wrong with the database file; empty when it is sound."""
    try:
        with closing(sqlite3.connect(path)) as db:
            rows = db.execute("PRAGMA integrity_check").fetchall()
    except sqlite3.DatabaseError as error:  # too damaged to even be read
        return [str(error)]
    return [] if rows == [("ok",)] else [str(row[0]) for row in rows]
