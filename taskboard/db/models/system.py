"""Infrastructure tables: named lock rows that serialize critical sections (see db/session.py)."""

from sqlalchemy import Unicode
from sqlalchemy.orm import Mapped, mapped_column

from taskboard.db.base import Base


class AppLock(Base):
    """One row per named lock. Updating the row holds a write lock on it until commit."""

    __tablename__ = "app_locks"

    name: Mapped[str] = mapped_column(Unicode(50), primary_key=True)
    counter: Mapped[int] = mapped_column(default=0)
