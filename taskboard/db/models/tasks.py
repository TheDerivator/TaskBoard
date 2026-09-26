"""Tasks, their helpers, and their placements in projects."""

from datetime import datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, LongName, Text, UTCDateTime, str_enum, utcnow
from taskboard.db.models.org import Section
from taskboard.db.models.people import Person
from taskboard.db.models.projects import Project, ProjectNode
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.task_keys import MAX_KEY_LENGTH


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)  # internal; never exposed
    key: Mapped[str] = mapped_column(Unicode(MAX_KEY_LENGTH), unique=True)  # public, "K7Q2MX"
    title: Mapped[str] = mapped_column(LongName)
    description: Mapped[str] = mapped_column(Text, default="")
    # Dense 1..N over all tasks: the one team-wide ranking. Not UNIQUE on purpose: a range shift
    # is one UPDATE, and some backends check uniqueness row by row during it.
    rank: Mapped[int] = mapped_column(index=True)
    status: Mapped[TaskStatus] = mapped_column(str_enum(TaskStatus), default=TaskStatus.IDEA)
    lead_person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012  (SQLAlchemy convention)

    lead: Mapped[Person] = relationship(foreign_keys=[lead_person_id])
    section: Mapped[Section] = relationship()
    helpers: Mapped[list[TaskHelper]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )
    placements: Mapped[list[Placement]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )


class TaskHelper(Base):
    """A person who helps on a task (the lead is never also a helper)."""

    __tablename__ = "task_helpers"

    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), primary_key=True, index=True)

    task: Mapped[Task] = relationship(back_populates="helpers")
    person: Mapped[Person] = relationship()


class Placement(Base):
    """Where a task sits in one project. At most one placement per (task, project)."""

    __tablename__ = "placements"
    __table_args__ = (
        UniqueConstraint("task_id", "project_id"),
        # The node must belong to the same project (not enforced when node_id is NULL = top level).
        ForeignKeyConstraint(
            ["node_id", "project_id"],
            ["project_nodes.id", "project_nodes.project_id"],
            name="fk_placements_node_same_project",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    node_id: Mapped[int | None] = mapped_column(index=True)

    task: Mapped[Task] = relationship(back_populates="placements")
    project: Mapped[Project] = relationship()
    node: Mapped[ProjectNode | None] = relationship(
        primaryjoin="Placement.node_id == ProjectNode.id",
        foreign_keys=[node_id],
        viewonly=True,
    )
