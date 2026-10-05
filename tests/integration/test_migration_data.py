"""Migrations also work on databases that already hold data (not only on empty ones)."""

from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

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


BEFORE_CHANGES = "43353ae16098"  # processes; the next revision lets posts belong to changes


def test_posts_keep_their_task_when_they_may_also_belong_to_changes(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "old.sqlite3")
    command.upgrade(alembic_config(url), BEFORE_CHANGES)
    database = Database(url)
    now = {"now": "2026-09-01 10:00:00"}
    with database.session(write=True) as s:
        for statement in (
            "INSERT INTO users (username, display_name, must_change_password, status, kind,"
            " is_builtin, created_at) VALUES ('jan', 'Jan', 0, 'active', 'regular', 0, :now)",
            "INSERT INTO departments (code, name, position) VALUES ('STL', 'STL', 0)",
            "INSERT INTO sections (department_id, name, position) VALUES (1, 'Quality', 0)",
            "INSERT INTO people (code, name, color, section_id, active)"
            " VALUES ('JA', 'Jan', '#2D5BA8', 1, 1)",
            "INSERT INTO tasks (key, title, description, rank, status, lead_person_id, section_id,"
            " created_at, updated_at, version) VALUES ('K7Q2MX', 'T', '', 1, 'idea', 1, 1, :now,"
            " :now, 1)",
            "INSERT INTO posts (task_id, author_user_id, created_at, body_md, is_update)"
            " VALUES (1, 1, :now, 'Hello', 0)",
            "INSERT INTO attachments (public_id, task_id, post_id, uploader_user_id, filename,"
            " content_type, size, created_at) VALUES ('ab12', 1, 1, 1, 'a.png', 'image/png', 3,"
            " :now)",
        ):
            s.execute(text(statement), now if ":now" in statement else {})
    database.dispose()

    upgrade_database(url)
    database = Database(url)
    with database.session() as s:
        assert s.execute(text("SELECT task_id, change_id FROM posts")).one() == (1, None)
        assert s.execute(text("SELECT task_id, change_id FROM attachments")).one() == (1, None)
    with pytest.raises(IntegrityError), database.session(write=True) as s:
        # Neither a task nor a change: refused by the new CHECK constraint.
        s.execute(
            text(
                "INSERT INTO posts (author_user_id, created_at, body_md, is_update)"
                " VALUES (1, :now, 'Orphan', 0)"
            ),
            now,
        )
    database.dispose()
