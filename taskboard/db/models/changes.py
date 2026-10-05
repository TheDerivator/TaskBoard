"""Process changes: one per change to a process, and its periods (tests and permanent changes).

A period is posted in the change's conversation, so each period row belongs to a post of that same
change (a composite foreign key makes that a database guarantee).
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, ForeignKey, ForeignKeyConstraint, Unicode
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, LongName, ShortText, Text, UTCDateTime, str_enum, utcnow
from taskboard.db.models.org import Process
from taskboard.db.models.people import Person
from taskboard.domain.changes import PeriodKind


class Change(Base):
    __tablename__ = "changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Public and fixed: process code + number ("LM-07"); kept when the change moves process.
    key: Mapped[str] = mapped_column(Unicode(20), unique=True)
    number: Mapped[int]  # the number in the key, counted per process code
    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id"), index=True)
    title: Mapped[str] = mapped_column(LongName)
    what_md: Mapped[str] = mapped_column(Text, default="")
    why_md: Mapped[str] = mapped_column(Text, default="")
    owner_person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012  (SQLAlchemy convention)

    process: Mapped[Process] = relationship()
    owner: Mapped[Person] = relationship()


class ChangePeriod(Base):
    """A test (with an end date) or a permanent process change (without one, until it ends)."""

    __tablename__ = "change_periods"
    __table_args__ = (
        # The post must be one of this change's posts.
        ForeignKeyConstraint(
            ["post_id", "change_id"],
            ["posts.id", "posts.change_id"],
            name="fk_change_periods_post_same_change",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(unique=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("changes.id"), index=True)
    kind: Mapped[PeriodKind] = mapped_column(str_enum(PeriodKind))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)  # inclusive
    label: Mapped[str] = mapped_column(ShortText)
    scope_tags: Mapped[list[Any]] = mapped_column(JSON, default=list)  # free text (DESIGN rule 4)
