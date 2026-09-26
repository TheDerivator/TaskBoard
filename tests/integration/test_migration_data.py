"""Migrations also work on databases that already hold data (not only on empty ones)."""

from pathlib import Path

from alembic import command
from sqlalchemy import text

from taskboard.db.migrate import alembic_config, upgrade_database
from taskboard.db.session import Database
from tests.conftest import sqlite_url

BEFORE_SSO = "867d060d677d"  # login_attempts; the next revision adds external_identities.groups


def test_adding_identity_groups_keeps_existing_links(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "old.sqlite3")
    command.upgrade(alembic_config(url), BEFORE_SSO)
    database = Database(url)
    with database.session(write=True) as s:
        s.execute(
            text(
                "INSERT INTO users (username, display_name, must_change_password, status, kind,"
                " is_builtin, created_at)"
                " VALUES ('jan', 'Jan', 0, 'active', 'regular', 0, '2026-09-01 10:00:00')"
            )
        )
        s.execute(
            text(
                "INSERT INTO external_identities (user_id, provider, subject, created_at)"
                " VALUES (1, 'entra', 'oid-1', '2026-09-01 10:00:00')"
            )
        )
    database.dispose()

    upgrade_database(url)
    database = Database(url)
    with database.session() as s:
        assert s.execute(text("SELECT groups FROM external_identities")).scalar() == "[]"
    database.dispose()
