"""Administration › Backups: what the backup folder holds, and how many backups to keep (D-100).

Needs `users.manage`. Backups are made and deleted by `python -m taskboard backup` (a scheduled
task), never by the web app; the folder is a server setting (`TASKBOARD_BACKUP_DIR`), only shown
here.
"""

from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from taskboard.db.base import utcnow
from taskboard.db.models import BackupSettings
from taskboard.domain.access import Permission
from taskboard.domain.backups import LIMITS, Retention
from taskboard.identity.principal import Principal
from taskboard.schemas.admin import (
    BackupOut,
    BackupOverview,
    RetentionIn,
    RetentionLimit,
    RetentionOut,
)
from taskboard.services import audit
from taskboard.services.backup import BackupFile, kept_as, list_backups
from taskboard.services.visibility import ensure_usable

OVERDUE_AFTER = timedelta(days=2)


def load_retention(session: Session) -> Retention:
    """The retention an administrator chose, or the defaults."""
    row = session.get(BackupSettings, 1)
    if row is None:
        return Retention()
    return Retention(newest=row.keep_newest, weekly=row.keep_weekly, monthly=row.keep_monthly)


def _read_folder(folder: Path) -> tuple[list[BackupFile], str | None]:
    """The backups in the folder, or why it cannot be read."""
    try:
        return list_backups(folder), None
    except FileNotFoundError:
        return [], "The folder does not exist or cannot be reached. The first backup creates it."
    except OSError as error:
        return [], f"The folder cannot be read: {error.strerror or error}."


class BackupAdminService:
    def __init__(self, session: Session, principal: Principal, folder: Path) -> None:
        self.session = session
        self.principal = principal
        self.folder = folder
        ensure_usable(principal)
        principal.require(Permission.USERS_MANAGE)

    def overview(self) -> BackupOverview:
        retention = load_retention(self.session)
        backups, problem = _read_folder(self.folder)
        reasons = kept_as(backups, retention)
        return BackupOverview(
            location=str(self.folder),
            problem=problem,
            backups=[
                BackupOut(
                    name=b.path.name, taken_at=b.taken_at, size=b.size, kept_as=reasons[b.path]
                )
                for b in backups
            ],
            total_size=sum(b.size for b in backups),
            overdue=not backups or utcnow() - backups[0].taken_at > OVERDUE_AFTER,
            retention=RetentionOut(
                newest=retention.newest, weekly=retention.weekly, monthly=retention.monthly
            ),
            limits={kind: RetentionLimit(min=b.low, max=b.high) for kind, b in LIMITS.items()},
        )

    def update_retention(self, data: RetentionIn) -> BackupOverview:
        """Takes effect at the next backup, which deletes what is no longer kept."""
        row = self.session.get(BackupSettings, 1)
        if row is None:
            row = BackupSettings(id=1)
            self.session.add(row)
        row.keep_newest, row.keep_weekly, row.keep_monthly = data.newest, data.weekly, data.monthly
        row.updated_at = utcnow()
        row.updated_by_user_id = self.principal.user_id
        audit.record(
            self.session,
            "backup.retention_changed",
            actor_user_id=self.principal.user_id,
            target_type="backups",
            **data.model_dump(),
        )
        self.session.commit()
        return self.overview()
