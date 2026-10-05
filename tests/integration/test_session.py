"""Engine setup: SQLite pragmas, UTC datetimes, serialized writers, long lists of ids."""

import threading
import time
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from taskboard.db.ids import in_ids
from taskboard.db.models import AuditEntry, Box
from taskboard.db.session import TASK_RANKING_LOCK, Database, acquire_lock
from tests.conftest import requires_sqlite


@requires_sqlite
def test_sqlite_pragmas(database: Database) -> None:
    with database.session() as s:
        assert s.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert s.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_datetimes_come_back_timezone_aware_utc(database: Database) -> None:
    moment = datetime(2026, 9, 26, 12, 30, tzinfo=UTC) + timedelta(microseconds=5)
    with database.session(write=True) as s:
        s.add(AuditEntry(action="test", actor_user_id=None, at=moment))
    with database.session() as s:
        stored = s.scalars(select(AuditEntry.at).where(AuditEntry.action == "test")).one()
    assert stored == moment
    assert stored.tzinfo is UTC


def test_naive_datetimes_are_refused(database: Database) -> None:
    with database.session(write=True) as s:
        s.add(AuditEntry(action="test", actor_user_id=None, at=datetime(2026, 1, 1)))
        with pytest.raises(StatementError):
            s.flush()
        s.rollback()


def test_write_sessions_wait_for_each_other(database: Database) -> None:
    """A second writer blocks until the first commits (BEGIN IMMEDIATE + busy timeout)."""
    first_holds_lock = threading.Event()
    timeline: list[str] = []

    def first_writer() -> None:
        with database.session(write=True) as s:
            acquire_lock(s, TASK_RANKING_LOCK)
            first_holds_lock.set()
            time.sleep(0.3)
            timeline.append("first commits")

    thread = threading.Thread(target=first_writer)
    thread.start()
    first_holds_lock.wait(5)
    with database.session(write=True) as s:
        acquire_lock(s, TASK_RANKING_LOCK)
        timeline.append("second got the lock")
    thread.join()
    assert timeline == ["first commits", "second got the lock"]


def test_any_number_of_ids_fits_in_one_statement(sample_database: Database) -> None:
    """MS SQL takes 2,100 parameters; `in_ids` writes ids into the SQL (tests/conftest.py fails
    any statement with more parameters, on every backend)."""
    with sample_database.session() as s:
        boxes = set(s.scalars(select(Box.id)))
        found = set(
            s.scalars(select(Box.id).where(in_ids(Box.id, [*boxes, *range(10**6, 10**6 + 5000)])))
        )
    assert found == boxes
    with pytest.raises(ValueError):
        in_ids(Box.id, ["1; DROP TABLE boxes"])  # type: ignore[list-item]
