"""Infrastructure tables: named lock rows that serialize critical sections (see db/session.py),
and how many backups to keep."""

from datetime import datetime

from sqlalchemy import ForeignKey, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from taskboard.db.base import Base, UTCDateTime


class AppLock(Base):
    """One row per named lock. Updating the row holds a write lock on it until commit."""

    __tablename__ = "app_locks"

    name: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    counter: Mapped[int] = mapped_column(default=0)


class BackupSettings(Base):
    """How many backups `python -m taskboard backup` keeps (domain/backups.py). At most one row,
    with id 1; without it the defaults apply. The backup folder itself is a server setting."""

    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    keep_newest: Mapped[int]
    keep_weekly: Mapped[int]
    keep_monthly: Mapped[int]
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
