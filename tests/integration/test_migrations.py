"""Migrations build the whole schema, match the models exactly, and can be rolled back."""

from pathlib import Path

from alembic import command
from sqlalchemy import inspect

from taskboard.db.migrate import alembic_config, check_models_match_migrations, upgrade_database
from taskboard.db.models import Base
from taskboard.db.session import Database
from tests.conftest import sqlite_url


def test_upgrade_creates_every_table(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    database = Database(url)
    tables = set(inspect(database.engine).get_table_names())
    database.dispose()
    assert set(Base.metadata.tables) <= tables


def test_models_and_migrations_agree(tmp_path: Path) -> None:
    """Fails when a model changed without a migration (run alembic revision --autogenerate)."""
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    check_models_match_migrations(url)


def test_downgrade_to_base_and_back(tmp_path: Path) -> None:
    url = sqlite_url(tmp_path / "fresh.sqlite3")
    upgrade_database(url)
    command.downgrade(alembic_config(url), "base")
    upgrade_database(url)
    check_models_match_migrations(url)
