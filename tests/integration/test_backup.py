"""Backup and restore: one archive with a consistent database snapshot and the uploaded images."""

import json
import zipfile
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import func, select

from taskboard.cli import main
from taskboard.config import Settings, get_settings
from taskboard.db.migrate import alembic_config, current_revision
from taskboard.db.models import Task
from taskboard.db.session import Database
from taskboard.services.attachments import AttachmentStore
from taskboard.services.backup import BackupError, create_backup, restore_backup
from taskboard.services.sample_data import load_sample_data
from tests.conftest import requires_sqlite, sqlite_url

pytestmark = requires_sqlite  # other databases are backed up with their own tools

BEFORE_SSO = "867d060d677d"


def task_count(url: str) -> int:
    database = Database(url)
    try:
        with database.session() as s:
            return s.scalar(select(func.count()).select_from(Task)) or 0
    finally:
        database.dispose()


def new_home(tmp_path: Path, name: str) -> tuple[str, Path]:
    """Database URL and uploads folder of another (empty) installation."""
    home = tmp_path / name
    return sqlite_url(home / "taskboard.sqlite3"), home / "uploads"


def test_a_backup_holds_the_database_and_the_images(
    settings: Settings, sample_database: Database, tmp_path: Path
) -> None:
    del sample_database
    report = create_backup(
        settings.resolved_database_url, settings.uploads_dir, tmp_path / "backups.zip"
    )
    assert report.with_database and report.uploads == 1
    with zipfile.ZipFile(report.path) as zf:
        names = sorted(zf.namelist())
        manifest = json.loads(zf.read("manifest.json"))
    assert names[:2] == ["manifest.json", "taskboard.sqlite3"]
    assert len(names) == 3 and names[2].startswith("uploads/")
    assert manifest["schema_revision"] == current_revision(settings.resolved_database_url)
    assert not (tmp_path / "backups.zip.partial").exists()


def test_restore_into_a_new_installation(
    settings: Settings, sample_database: Database, tmp_path: Path
) -> None:
    del sample_database
    archive = create_backup(
        settings.resolved_database_url, settings.uploads_dir, tmp_path / "b.zip"
    ).path
    url, uploads = new_home(tmp_path, "new")
    report = restore_backup(archive, url, uploads)
    assert report.with_database and report.uploads == 1 and report.set_aside == []
    assert task_count(url) == task_count(settings.resolved_database_url) == 11
    assert [p.name for p in uploads.iterdir()] == [p.name for p in settings.uploads_dir.iterdir()]


def test_existing_data_is_only_replaced_on_request_and_then_kept(
    settings: Settings, database: Database, tmp_path: Path
) -> None:
    empty_board = create_backup(
        settings.resolved_database_url, settings.uploads_dir, tmp_path / "empty.zip"
    ).path
    with database.session(write=True) as s:  # afterwards, the sample board arrives
        load_sample_data(s, store=AttachmentStore(settings.uploads_dir))
    with pytest.raises(BackupError, match="already has data"):
        restore_backup(empty_board, settings.resolved_database_url, settings.uploads_dir)

    report = restore_backup(
        empty_board, settings.resolved_database_url, settings.uploads_dir, replace=True
    )
    database_aside, uploads_aside = report.set_aside
    assert task_count(sqlite_url(database_aside)) == 11  # the replaced board is kept
    assert len(list(uploads_aside.iterdir())) == 1
    assert list(settings.uploads_dir.iterdir()) == []


def test_backups_of_older_versions_are_upgraded(tmp_path: Path) -> None:
    old_url = sqlite_url(tmp_path / "old" / "taskboard.sqlite3")
    (tmp_path / "old").mkdir()
    command.upgrade(alembic_config(old_url), BEFORE_SSO)
    archive = create_backup(old_url, tmp_path / "old" / "uploads", tmp_path / "old.zip").path

    url, uploads = new_home(tmp_path, "new")
    restore_backup(archive, url, uploads)
    head = ScriptDirectory.from_config(alembic_config(url)).get_current_head()
    assert current_revision(url) == head != BEFORE_SSO


def test_backups_from_newer_versions_are_refused(tmp_path: Path) -> None:
    archive = tmp_path / "future.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": 1, "schema_revision": "f00000000000"}))
    url, uploads = new_home(tmp_path, "new")
    with pytest.raises(BackupError, match="newer version"):
        restore_backup(archive, url, uploads)


@pytest.mark.parametrize(
    "entry", ["../escape.txt", "uploads/../../escape", "C:/Windows/evil.dll", "uploads/a.b"]
)
def test_archives_with_unexpected_entries_are_refused(tmp_path: Path, entry: str) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": 1}))
        zf.writestr(entry, b"x")
    url, uploads = new_home(tmp_path, "new")
    with pytest.raises(BackupError, match="unexpected entry"):
        restore_backup(archive, url, uploads)
    assert not (tmp_path / "escape.txt").exists()


def test_the_cli_backs_up_and_restores(
    settings: Settings,
    sample_database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del sample_database
    monkeypatch.setenv("TASKBOARD_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("TASKBOARD_DATABASE_URL", settings.resolved_database_url)
    get_settings.cache_clear()
    try:
        assert main(["backup"]) == 0
        [archive] = (settings.data_dir / "backups").iterdir()
        assert main(["restore", str(archive)]) == 1
        assert main(["restore", str(archive), "--replace"]) == 0
    finally:
        get_settings.cache_clear()
    out = capsys.readouterr().out
    assert "Wrote" in out and "Restore failed: TaskBoard already has data here" in out
    assert "Restored the database and 1 uploaded images" in out
    assert "The data it replaced is kept at" in out
