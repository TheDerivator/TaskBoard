"""Back up and restore everything TaskBoard stores: the database and the uploaded images.

A backup is one zip file holding `manifest.json`, `taskboard.sqlite3` (a consistent snapshot,
taken while the app keeps running, that passed SQLite's integrity check) and `uploads/`. In the
backup folder, backups are named after the time they were taken (UTC), and older ones are deleted
as the retention allows (domain/backups.py); other files there are left alone. A restore first
sets aside what it replaces (`<name>.before-restore-<time>`, next to the original), then brings the
schema up to date, so backups made by older versions restore too. With a non-SQLite database the
archive holds the uploads only; back the database up with its own tools (docs/OPERATIONS.md).
"""

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from pathlib import Path
from typing import Any

from taskboard import __version__
from taskboard.db.base import utcnow
from taskboard.db.migrate import current_revision, is_known_revision, upgrade_database
from taskboard.db.sqlite_files import copy_database, database_problems, sqlite_file
from taskboard.domain.backups import KeptAs, Retention, kept_backups

FORMAT = 1
MANIFEST = "manifest.json"
DATABASE = "taskboard.sqlite3"
STAMP = "%Y%m%d-%H%M%S"
_UPLOAD_ENTRY = re.compile(r"^uploads/[A-Za-z0-9]+$")
_BACKUP_NAME = re.compile(r"^taskboard-backup-(\d{8}-\d{6})\.zip$")


class BackupError(Exception):
    """A backup or restore that cannot be done (message safe to show)."""


@dataclass(frozen=True, slots=True)
class BackupReport:
    path: Path
    with_database: bool
    uploads: int


@dataclass(frozen=True, slots=True)
class BackupFile:
    path: Path
    taken_at: datetime  # UTC, from the file name
    size: int


@dataclass(frozen=True, slots=True)
class PruneReport:
    removed: list[Path]
    failed: list[tuple[Path, str]]  # and why each could not be deleted


@dataclass(frozen=True, slots=True)
class RestoreReport:
    created_at: str
    with_database: bool
    uploads: int
    set_aside: list[Path]


def _stamp() -> str:
    return utcnow().strftime(STAMP)


def _uploads(uploads_dir: Path) -> list[Path]:
    """Stored images (flat, alphanumeric names); half-written `*.part` files are skipped."""
    if not uploads_dir.is_dir():
        return []
    return sorted(p for p in uploads_dir.iterdir() if p.is_file() and p.name.isalnum())


def create_backup(database_url: str, uploads_dir: Path, destination: Path) -> BackupReport:
    """Write a backup archive; `destination` is a .zip file, or a folder to put a new one in.

    Nothing is left behind when it fails, e.g. on a database that fails the integrity check.
    """
    archive = (
        destination / f"taskboard-backup-{_stamp()}.zip" if destination.is_dir() else destination
    )
    database = sqlite_file(database_url)
    if database is not None and not database.exists():
        raise BackupError(f"there is no database at {database}")
    manifest: dict[str, Any] = {
        "format": FORMAT,
        "app_version": __version__,
        "created_at": utcnow().isoformat(timespec="seconds"),
        "schema_revision": current_revision(database_url),
        "database": DATABASE if database is not None else None,
    }
    partial = archive.with_name(f"{archive.name}.partial")
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            tempfile.TemporaryDirectory() as scratch,
            zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as zf,
        ):
            if database is not None:  # first, so every image it refers to exists already
                snapshot = Path(scratch) / DATABASE
                copy_database(database, snapshot)
                if problems := database_problems(snapshot):
                    raise BackupError(
                        f"the database failed SQLite's integrity check ({problems[0]})"
                    )
                zf.write(snapshot, DATABASE)
            uploads = 0
            for path in _uploads(uploads_dir):
                try:  # images are compressed already
                    zf.write(path, f"uploads/{path.name}", compress_type=zipfile.ZIP_STORED)
                except FileNotFoundError:  # deleted meanwhile, e.g. a draft nobody posted
                    continue
                uploads += 1
            zf.writestr(MANIFEST, json.dumps(manifest | {"uploads": uploads}, indent=2))
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(archive)
    return BackupReport(path=archive, with_database=database is not None, uploads=uploads)


def list_backups(folder: Path) -> list[BackupFile]:
    """The backups in the backup folder, newest first (raises OSError if it cannot be read)."""
    backups: list[BackupFile] = []
    for path in folder.iterdir():
        match = _BACKUP_NAME.match(path.name)
        if not match or not path.is_file():
            continue
        try:
            taken_at = datetime.strptime(match[1], STAMP).replace(tzinfo=UTC)
        except ValueError:  # a name like it with an impossible date
            continue
        backups.append(BackupFile(path=path, taken_at=taken_at, size=path.stat().st_size))
    return sorted(backups, key=lambda b: b.taken_at, reverse=True)


def kept_as(
    backups: list[BackupFile], retention: Retention, tz: tzinfo | None = None
) -> dict[Path, list[KeptAs]]:
    """Why each backup is kept (nothing: the next backup deletes it). Weeks and months are the
    server's own (`tz`, by default its local time zone)."""
    local = {b.taken_at.astimezone(tz): b.path for b in backups}
    kept = kept_backups(local, retention)
    return {path: kept.get(moment, []) for moment, path in local.items()}


def prune_backups(folder: Path, retention: Retention, tz: tzinfo | None = None) -> PruneReport:
    """Delete the backups the retention does not keep."""
    report = PruneReport(removed=[], failed=[])
    for path, reasons in kept_as(list_backups(folder), retention, tz).items():
        if reasons:
            continue
        try:
            path.unlink()
        except OSError as error:
            report.failed.append((path, error.strerror or str(error)))
        else:
            report.removed.append(path)
    return report


def _read_manifest(zf: zipfile.ZipFile) -> dict[str, Any]:
    for name in zf.namelist():
        if name not in (MANIFEST, DATABASE) and not _UPLOAD_ENTRY.match(name):
            raise BackupError(f"not a TaskBoard backup: unexpected entry {name!r}")
    try:
        manifest: dict[str, Any] = json.loads(zf.read(MANIFEST))
    except KeyError, ValueError:
        raise BackupError("not a TaskBoard backup: no readable manifest.json") from None
    if manifest.get("format") != FORMAT:
        raise BackupError(f"unsupported backup format {manifest.get('format')!r}")
    revision = manifest.get("schema_revision")
    if revision and not is_known_revision(revision):
        raise BackupError("this backup was made by a newer version of TaskBoard; upgrade first")
    return manifest


def _has_content(path: Path) -> bool:
    return path.is_file() or (path.is_dir() and any(path.iterdir()))


def restore_backup(
    archive: Path, database_url: str, uploads_dir: Path, *, replace: bool = False
) -> RestoreReport:
    """Put the backup's database and uploads in place. Stop the app first.

    Existing data is only replaced with `replace`, and is then set aside rather than deleted.
    """
    if not archive.is_file():
        raise BackupError(f"there is no backup at {archive}")
    database = sqlite_file(database_url)
    with zipfile.ZipFile(archive) as zf, tempfile.TemporaryDirectory() as scratch:
        manifest = _read_manifest(zf)
        with_database = manifest.get("database") == DATABASE
        if with_database and database is None:
            raise BackupError(
                "this backup holds a SQLite database, but TaskBoard is set up for another database"
            )
        replaced = [p for p in (database if with_database else None, uploads_dir) if p]
        if not replace and any(_has_content(p) for p in replaced):
            raise BackupError(
                "TaskBoard already has data here; use --replace to set it aside and restore"
            )
        zf.extractall(scratch)  # every entry name was checked above
        stamp = _stamp()
        set_aside: list[Path] = []
        if with_database and database is not None:
            if database.exists():
                aside = database.with_name(f"{database.name}.before-restore-{stamp}")
                copy_database(database, aside)
                set_aside.append(aside)
            copy_database(Path(scratch) / DATABASE, database)
        if _has_content(uploads_dir):
            aside = uploads_dir.with_name(f"{uploads_dir.name}.before-restore-{stamp}")
            uploads_dir.rename(aside)
            set_aside.append(aside)
        uploads_dir.mkdir(parents=True, exist_ok=True)
        restored = _uploads(Path(scratch) / "uploads")
        for path in restored:
            shutil.move(path, uploads_dir / path.name)
    if with_database:
        upgrade_database(database_url)
    return RestoreReport(
        created_at=str(manifest.get("created_at")),
        with_database=with_database,
        uploads=len(restored),
        set_aside=set_aside,
    )
