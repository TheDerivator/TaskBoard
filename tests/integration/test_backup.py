"""Backup and restore: one archive with a consistent, sound database snapshot and the uploaded
images; the backup folder keeps what the retention says (D-100)."""

import json
import sqlite3
import zipfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text

from taskboard.cli import main
from taskboard.config import Settings, get_settings
from taskboard.db.base import utcnow
from taskboard.db.migrate import alembic_config, current_revision
from taskboard.db.models import (
    BackupSettings,
    Box,
    Change,
    ChangePeriod,
    Release,
    ReleaseItem,
    Revision,
    Task,
    User,
)
from taskboard.db.session import Database
from taskboard.db.sqlite_files import database_problems
from taskboard.domain.backups import Retention
from taskboard.services import backup
from taskboard.services.attachments import AttachmentStore, store_image
from taskboard.services.backup import (
    BackupError,
    create_backup,
    list_backups,
    prune_backups,
    restore_backup,
)
from taskboard.services.sample_data import defect_map_png, load_sample_data
from tests.conftest import requires_sqlite, sqlite_url
from tests.helpers import fake_backups

pytestmark = requires_sqlite  # other databases are backed up with their own tools

BEFORE_SSO = "867d060d677d"


def task_count(url: str) -> int:
    database = Database(url)
    try:
        with database.session() as s:
            return s.scalar(select(func.count()).select_from(Task)) or 0
    finally:
        database.dispose()


def counts(url: str) -> dict[str, int]:
    """Rows of what process changes and process knowledge store (M11-M18)."""
    database = Database(url)
    try:
        with database.session() as s:
            models = (Change, ChangePeriod, Box, Revision, Release, ReleaseItem)
            return {
                m.__tablename__: s.scalar(select(func.count()).select_from(m)) or 0 for m in models
            }
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


def test_process_changes_and_knowledge_come_back_with_their_images(
    settings: Settings, sample_database: Database, tmp_path: Path
) -> None:
    with sample_database.session(write=True) as s:
        mould = s.scalars(select(Box).where(Box.key == "mould")).one()
        admin = s.scalars(select(User.id).where(User.username == "admin")).one()
        image = store_image(
            AttachmentStore(settings.uploads_dir),
            "level.png",
            defect_map_png(20, 10),
            box_id=mould.id,
            uploader_user_id=admin,
        )
        s.add(image)
    before = counts(settings.resolved_database_url)
    assert before["releases"] == 3 and before["release_items"] > 0
    archive = create_backup(
        settings.resolved_database_url, settings.uploads_dir, tmp_path / "b.zip"
    ).path
    url, uploads = new_home(tmp_path, "new")
    report = restore_backup(archive, url, uploads)
    assert report.uploads == 2  # the task conversation's image and the box's
    assert counts(url) == before


def test_an_image_deleted_meanwhile_is_left_out(
    settings: Settings, sample_database: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An unposted draft image removed between listing the uploads and zipping them."""
    del sample_database
    [image] = settings.uploads_dir.iterdir()
    gone = settings.uploads_dir / "f00dcafe"
    monkeypatch.setattr(backup, "_uploads", lambda _folder: [gone, image])
    report = create_backup(settings.resolved_database_url, settings.uploads_dir, tmp_path / "b.zip")
    with zipfile.ZipFile(report.path) as zf:
        assert json.loads(zf.read("manifest.json"))["uploads"] == report.uploads == 1
        assert f"uploads/{image.name}" in zf.namelist()


def test_a_damaged_database_is_not_backed_up(tmp_path: Path) -> None:
    path = tmp_path / "damaged.sqlite3"
    with closing(sqlite3.connect(path)) as db:
        db.execute("create table t (id integer primary key, name text)")
        db.execute("create index ix_t_name on t (name)")
        db.executemany("insert into t (name) values (?)", [(f"name {i:05}",) for i in range(3000)])
        db.commit()
    data = bytearray(path.read_bytes())
    data[5 * 4096 : 5 * 4096 + 200] = b"\xab" * 200  # garbage in the middle of a table page
    path.write_bytes(bytes(data))
    assert database_problems(path)

    with pytest.raises(BackupError, match="integrity check"):
        create_backup(sqlite_url(path), tmp_path / "uploads", tmp_path / "backups")
    assert not (tmp_path / "backups").exists() or list((tmp_path / "backups").iterdir()) == []
    assert database_problems(tmp_path / "missing.sqlite3") == []  # created empty: sound


def test_the_backup_folder_keeps_what_the_retention_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "backups"
    old, monthly, weekly, gone, newer, newest = fake_backups(
        folder, "2025-01-10", "2025-02-10", "2025-03-03", "2025-03-04", "2025-03-05", "2025-03-06"
    )
    others = ["pristine-demo.zip", "notes.txt", "taskboard-backup-20251332-120000.zip"]
    for name in [*others, f"{newest}.partial"]:
        (folder / name).write_bytes(b"not a backup of the folder")
    backups = list_backups(folder)
    assert [b.path.name for b in backups] == [newest, newer, gone, weekly, monthly, old]
    assert backups[0].taken_at == datetime(2025, 3, 6, 12, tzinfo=UTC) and backups[0].size == 6000

    report = prune_backups(folder, Retention(newest=2, weekly=1, monthly=2), tz=UTC)
    assert [p.name for p in report.removed] == sorted([gone, old], reverse=True)
    assert report.failed == []
    assert sorted(p.name for p in folder.iterdir()) == sorted(
        [newest, newer, weekly, monthly, *others, f"{newest}.partial"]
    )

    def refuse(path: Path) -> None:
        raise PermissionError(13, "Access is denied", str(path))

    monkeypatch.setattr(Path, "unlink", refuse)
    report = prune_backups(folder, Retention(newest=2, weekly=1, monthly=1), tz=UTC)
    assert report.removed == [] and report.failed == [(folder / monthly, "Access is denied")]


def run_cli(monkeypatch: pytest.MonkeyPatch, settings: Settings, *args: str, **env: str) -> int:
    monkeypatch.setenv("TASKBOARD_DATA_DIR", str(settings.data_dir))
    monkeypatch.setenv("TASKBOARD_DATABASE_URL", settings.resolved_database_url)
    for name, value in env.items():
        monkeypatch.setenv(f"TASKBOARD_{name}", value)
    get_settings.cache_clear()
    try:
        return main(list(args))
    finally:
        get_settings.cache_clear()


def test_the_cli_deletes_the_backups_no_longer_kept(
    settings: Settings,
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The retention an administrator chose applies; the newest backup is the one just made."""
    folder = tmp_path / "share" / "TaskBoard"
    names = fake_backups(folder, "2020-01-06", "2020-01-07", "2020-02-03")
    with database.session(write=True) as s:
        s.add(
            BackupSettings(id=1, keep_newest=2, keep_weekly=1, keep_monthly=1, updated_at=utcnow())
        )

    assert run_cli(monkeypatch, settings, "backup", "--output", str(tmp_path)) == 0
    assert sorted(p.name for p in folder.iterdir()) == names  # an extra backup elsewhere

    assert run_cli(monkeypatch, settings, "backup", BACKUP_DIR=str(folder)) == 0
    [made] = [b.path.name for b in list_backups(folder) if b.taken_at.year > 2020]
    assert sorted(p.name for p in folder.iterdir()) == sorted([made, names[2]])
    out = capsys.readouterr().out
    assert f"Deleted {names[0]}: no longer kept." in out and f"Deleted {names[1]}" in out


def test_the_cli_says_when_the_backup_folder_is_out_of_reach(
    settings: Settings,
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    del database
    blocker = tmp_path / "a file"
    blocker.write_text("not a folder")
    assert run_cli(monkeypatch, settings, "backup", BACKUP_DIR=str(blocker / "backups")) == 1
    assert capsys.readouterr().out.startswith("Backup failed: ")


def test_the_backup_is_kept_when_cleaning_up_fails(
    settings: Settings,
    database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """New code, but the service has not yet upgraded the schema (no retention table)."""
    with database.session(write=True) as s:
        s.execute(text("DROP TABLE backup_settings"))
    folder = tmp_path / "backups"
    old = fake_backups(folder, "2020-01-06", "2020-01-07", "2020-01-08")
    assert run_cli(monkeypatch, settings, "backup", BACKUP_DIR=str(folder)) == 1
    assert len(list_backups(folder)) == 4  # the new one, and nothing deleted
    assert all((folder / name).exists() for name in old)
    out = capsys.readouterr().out
    assert out.startswith("Wrote ") and "Older backups were not cleaned up" in out
