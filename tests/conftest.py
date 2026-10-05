"""Shared pytest fixtures: isolated settings and databases, sessions, sample data, an HTTP client.

A template database is migrated and seeded once per test run; each test gets its own copy (a
file copy is much faster than running the migrations again).

With `TASKBOARD_TEST_DATABASE_URL` set (e.g. an empty MS SQL database, to prove portability), the
tests use that database instead: it is migrated once and emptied before every test. Tests
about SQLite itself are skipped then (`requires_sqlite`).
"""

import os
import shutil
from collections.abc import Generator, Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from taskboard.config import Environment, Settings
from taskboard.db.base import Base
from taskboard.db.session import Database
from taskboard.services.attachments import AttachmentStore
from taskboard.services.sample_data import load_sample_data
from taskboard.services.setup import prepare_database
from taskboard.web import create_app
from taskboard.web.csrf import CSRF_COOKIE, CSRF_HEADER

TEST_ADMIN_PASSWORD = "admin-password-for-tests"
# "Today" in the design's sample data; tests pin the server's date to it.
SAMPLE_TODAY = date(2026, 10, 3)
DB_FILENAME = "taskboard.sqlite3"

MSSQL_MAX_PARAMETERS = 2100


@event.listens_for(Engine, "before_cursor_execute")
def _portable_parameter_count(
    conn: object,
    cursor: object,
    statement: str,
    parameters: object,
    context: object,
    executemany: bool,
) -> None:
    """MS SQL refuses a statement with more than 2,100 parameters, SQLite takes 32,766: fail any
    test that sends more, so big id lists cannot pass here and break there. (Bulk INSERTs are
    left out: SQLAlchemy sizes their batches per database.)"""
    if executemany or statement.lstrip()[:6].upper() == "INSERT":
        return
    count = len(parameters) if isinstance(parameters, (tuple, list, dict)) else 0
    assert count <= MSSQL_MAX_PARAMETERS, (
        f"{count} parameters (MS SQL takes {MSSQL_MAX_PARAMETERS})"
    )


EXTERNAL_DATABASE_URL = os.environ.get("TASKBOARD_TEST_DATABASE_URL") or None

requires_sqlite = pytest.mark.skipif(
    EXTERNAL_DATABASE_URL is not None and not EXTERNAL_DATABASE_URL.startswith("sqlite"),
    reason="about SQLite itself",
)


def sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def prepare(url: str) -> None:
    """Migrate and seed the built-in data (roles, admin, anonymous)."""
    database = Database(url)
    prepare_database(database, initial_admin_password=TEST_ADMIN_PASSWORD)
    database.dispose()  # for SQLite: closing the last connection checkpoints the WAL


def empty_database(url: str) -> None:
    """Delete every row (children first); the schema and its migration version stay."""
    engine = create_engine(url)
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    engine.dispose()


@pytest.fixture(scope="session")
def template_db(tmp_path_factory: pytest.TempPathFactory) -> Path | None:
    if EXTERNAL_DATABASE_URL:
        prepare(EXTERNAL_DATABASE_URL)
        return None
    path = tmp_path_factory.mktemp("template") / DB_FILENAME
    prepare(sqlite_url(path))
    return path


@pytest.fixture
def settings(tmp_path: Path, template_db: Path | None) -> Settings:
    """Settings pointing at a fresh copy of the template database in a temporary data dir."""
    if template_db is None:
        assert EXTERNAL_DATABASE_URL
        empty_database(EXTERNAL_DATABASE_URL)
        prepare(EXTERNAL_DATABASE_URL)
    else:
        shutil.copyfile(template_db, tmp_path / DB_FILENAME)
    return Settings(
        environment=Environment.TEST,
        data_dir=tmp_path,
        database_url=EXTERNAL_DATABASE_URL,
        initial_admin_password=SecretStr(TEST_ADMIN_PASSWORD),
        today=SAMPLE_TODAY,
        _env_file=None,  # pyright: ignore[reportCallIssue]
    )


@pytest.fixture
def database(settings: Settings) -> Iterator[Database]:
    db = Database(settings.resolved_database_url)
    yield db
    db.dispose()


@pytest.fixture
def session(database: Database) -> Iterator[Session]:
    """A write session; the test decides when to commit."""
    with database.new_session(write=True) as s:
        yield s


@pytest.fixture
def sample_database(database: Database, settings: Settings) -> Database:
    """The database with the design's sample board loaded (including its image attachment)."""
    with database.session(write=True) as s:
        assert load_sample_data(s, store=AttachmentStore(settings.uploads_dir))
    return database


def start_client(app: FastAPI) -> Generator[TestClient]:
    """A client that behaves like the frontend: it echoes the CSRF cookie in the header."""
    with TestClient(app) as test_client:
        test_client.get("/api/health")  # receive the CSRF cookie
        test_client.headers[CSRF_HEADER] = test_client.cookies[CSRF_COOKIE]
        yield test_client


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    yield from start_client(create_app(settings))
