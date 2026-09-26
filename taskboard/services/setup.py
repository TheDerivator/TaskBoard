"""Bring a database up to date: apply migrations, then create the built-in data."""

from taskboard.db.migrate import upgrade_database
from taskboard.db.session import Database
from taskboard.services.seed import SeedReport, seed_builtins


def prepare_database(database: Database, *, initial_admin_password: str | None) -> SeedReport:
    upgrade_database(database.url)
    with database.session(write=True) as session:
        return seed_builtins(session, initial_admin_password=initial_admin_password)
