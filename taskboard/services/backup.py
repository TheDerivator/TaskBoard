"""Back up and restore everything TaskBoard stores: the database and the uploaded images.

A backup is one zip file holding `manifest.json`, `taskboard.sqlite3` (a consistent snapshot,
taken while the app keeps running) and `uploads/`. A restore first sets aside what it replaces
(`<name>.before-restore-<time>`, next to the original), then brings the schema up to date, so
backups made by older versions restore too. With a non-SQLite database the archive holds the
uploads only; back the database up with its own tools (docs/OPERATIONS.md).
"""

import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from taskboard import __version__
from taskboard.db.base import utcnow
from taskboard.db.migrate import current_revision, is_known_revision, upgrade_database
from taskboard.db.sqlite_files import copy_database, sqlite_file

FORMAT = 1
MANIFEST = "manifest.json"
DATABASE = "taskboard.sqlite3"
_UPLOAD_ENTRY = re.compile(r"^uploads/[A-Za-z0-9]+$")


class BackupError(Exception):
    """A backup or restore that cannot be done (message safe to show)."""


@dataclass(frozen=True, slots=True)
class BackupReport:
    path: Path
    with_database: bool
    uploads: int


@dataclass(frozen=True, slots=True)
class RestoreReport:
    created_at: str
    with_database: bool
    uploads: int
    set_aside: list[Path]


def _stamp() -> str:
    return utcnow().strftime("%Y%m%d-%H%M%S")


def _uploads(uploads_dir: Path) -> list[Path]:
    """Stored images (flat, alphanumeric names); half-written `*.part` files are skipped."""
    if not uploads_dir.is_dir():
        return []
    return sorted(p for p in uploads_dir.iterdir() if p.is_file() and p.name.isalnum())


def create_backup(database_url: str, uploads_dir: Path, destination: Path) -> BackupReport:
    """Write a backup archive; `destination` is a .zip file, or a folder to put a new one in."""
    archive = (
        destination / f"taskboard-backup-{_stamp()}.zip" if destination.is_dir() else destination
    )
    database = sqlite_file(database_url)
    if database is not None and not database.exists():
        raise BackupError(f"there is no database at {database}")
    uploads = _uploads(uploads_dir)
    manifest = {
        "format": FORMAT,
        "app_version": __version__,
        "created_at": utcnow().isoformat(timespec="seconds"),
        "schema_revision": current_revision(database_url),
        "database": DATABASE if database is not None else None,
        "uploads": len(uploads),
    }
    partial = archive.with_name(f"{archive.name}.partial")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with (
        tempfile.TemporaryDirectory() as scratch,
        zipfile.ZipFile(partial, "w", compression=zipfile.ZIP_DEFLATED) as zf,
    ):
        zf.writestr(MANIFEST, json.dumps(manifest, indent=2))
        if database is not None:
            snapshot = Path(scratch) / DATABASE
            copy_database(database, snapshot)
            zf.write(snapshot, DATABASE)
        for path in uploads:  # images are compressed already
            zf.write(path, f"uploads/{path.name}", compress_type=zipfile.ZIP_STORED)
    partial.replace(archive)
    return BackupReport(path=archive, with_database=database is not None, uploads=len(uploads))


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
