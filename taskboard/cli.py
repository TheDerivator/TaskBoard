"""Command line interface: `python -m taskboard <command>`.

serve                       run the web server
db upgrade                  apply database migrations
seed [--sample] [--demo-password PW]
                            create built-in roles/users; optionally load the sample board
backup [--output PATH]      write a backup archive (database + uploaded images)
restore ARCHIVE [--replace] restore a backup archive (stop the server first)
"""

import argparse
from collections.abc import Sequence
from pathlib import Path

from taskboard.config import get_settings
from taskboard.db.session import Database
from taskboard.services.attachments import AttachmentStore
from taskboard.services.backup import BackupError, create_backup, restore_backup
from taskboard.services.sample_data import load_sample_data
from taskboard.services.setup import prepare_database

# Windows issues tickets of up to 48,000 bytes (MaxTokenSize), sent base64-encoded: 64 kB.
NEGOTIATE_HEADER_LIMIT = 128 * 1024


def _serve(args: argparse.Namespace) -> int:
    import uvicorn  # imported lazily: other commands don't need the server

    settings = get_settings()
    if bool(settings.tls_certfile) != bool(settings.tls_keyfile):
        print("HTTPS needs both TASKBOARD_TLS_CERTFILE and TASKBOARD_TLS_KEYFILE.")
        return 1
    uvicorn.run(
        "taskboard.web:create_app",
        factory=True,
        host=args.host or settings.host,
        port=args.port or settings.port,
        reload=args.reload,
        proxy_headers=False,  # the app reads forwarded headers itself (taskboard/api/client.py)
        ssl_certfile=str(settings.tls_certfile) if settings.tls_certfile else None,
        ssl_keyfile=str(settings.tls_keyfile) if settings.tls_keyfile else None,
        # Windows sign-in: a Kerberos ticket travels in a request header, and grows with the
        # user's group memberships well past the default limit of 16 kB for all headers.
        h11_max_incomplete_event_size=NEGOTIATE_HEADER_LIMIT if settings.windows_auth else None,
    )
    return 0


def _database() -> Database:
    return Database(get_settings().resolved_database_url)


def _db_upgrade(_args: argparse.Namespace) -> int:
    from taskboard.db.migrate import upgrade_database

    database = _database()
    upgrade_database(database.url)
    database.dispose()
    print("Database schema is up to date.")
    return 0


def _seed(args: argparse.Namespace) -> int:
    settings = get_settings()
    database = _database()
    admin_password = settings.initial_admin_password
    report = prepare_database(
        database,
        initial_admin_password=admin_password.get_secret_value() if admin_password else None,
    )
    for item in report.created:
        print(f"created {item}")
    if report.generated_admin_password:
        print(f"Admin password (change it at first login): {report.generated_admin_password}")
    if args.sample:
        with database.session(write=True) as session:
            loaded = load_sample_data(
                session,
                demo_password=args.demo_password,
                store=AttachmentStore(settings.uploads_dir),
                today=settings.current_date(),  # process changes then look current
            )
        print("Loaded the sample board." if loaded else "Board is not empty: sample not loaded.")
    database.dispose()
    return 0


def _backup(args: argparse.Namespace) -> int:
    settings = get_settings()
    destination = args.output or settings.data_dir / "backups"
    if args.output is None:
        destination.mkdir(parents=True, exist_ok=True)
    try:
        report = create_backup(settings.resolved_database_url, settings.uploads_dir, destination)
    except BackupError as error:
        print(f"Backup failed: {error}")
        return 1
    print(f"Wrote {report.path} ({report.uploads} uploaded images).")
    if not report.with_database:
        print("The database is not SQLite: back it up with its own tools (docs/OPERATIONS.md).")
    return 0


def _restore(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        report = restore_backup(
            args.archive,
            settings.resolved_database_url,
            settings.uploads_dir,
            replace=args.replace,
        )
    except BackupError as error:
        print(f"Restore failed: {error}")
        return 1
    what = "the database and " if report.with_database else ""
    print(
        f"Restored {what}{report.uploads} uploaded images from the backup of {report.created_at}."
    )
    for path in report.set_aside:
        print(f"The data it replaced is kept at {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m taskboard",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the web server")
    serve.add_argument("--host", help="interface to bind (default: TASKBOARD_HOST or 127.0.0.1)")
    serve.add_argument("--port", type=int, help="port (default: TASKBOARD_PORT or 8000)")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (dev only)")
    serve.set_defaults(handler=_serve)

    db = commands.add_parser("db", help="database maintenance")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("upgrade", help="apply migrations").set_defaults(handler=_db_upgrade)

    seed = commands.add_parser("seed", help="create built-in data, optionally the sample board")
    seed.add_argument("--sample", action="store_true", help="load the sample board if empty")
    seed.add_argument(
        "--demo-password", help="let the sample people log in with this password (demos only)"
    )
    seed.set_defaults(handler=_seed)

    backup = commands.add_parser("backup", help="write a backup archive (safe while running)")
    backup.add_argument(
        "--output", type=Path, help="a .zip file or a folder (default: <data dir>/backups)"
    )
    backup.set_defaults(handler=_backup)

    restore = commands.add_parser("restore", help="restore a backup archive (stop the server)")
    restore.add_argument("archive", type=Path, help="the backup .zip file")
    restore.add_argument(
        "--replace", action="store_true", help="set existing data aside (it is kept) and restore"
    )
    restore.set_defaults(handler=_restore)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.handler(args)
