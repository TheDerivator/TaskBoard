"""Process knowledge: kinds and link types, the boxes of each process's map (and the defect
catalogue), typed links, controls, external links, references from tasks and changes, revisions
and releases.

A map box belongs to a process; its tree has exactly one root (the box without a parent), and a
parent is always in the same process (composite key). A defect has no process and no parent: it
names its own section (D-080), whose department's catalogue it belongs to.
"""

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Unicode,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import (
    Base,
    LongName,
    ShortText,
    Text,
    UTCDateTime,
    str_enum,
    utcnow,
)
from taskboard.domain.knowledge import (
    MAX_KEY_LENGTH,
    BoxRole,
    ControlKind,
    ExternalLinkKind,
    LinkRole,
    ObjectType,
    ReferenceRole,
)

Url = Unicode(2000)


class BoxKind(Base):
    """A kind of box (Process step, Knowledge, ...). Built-in kinds are seeded; admins add more."""

    __tablename__ = "box_kinds"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(40), unique=True)
    name: Mapped[str] = mapped_column(ShortText)
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[BoxRole] = mapped_column(str_enum(BoxRole))
    style: Mapped[str] = mapped_column(Unicode(20))
    has_facts: Mapped[bool] = mapped_column(default=False)
    has_main_url: Mapped[bool] = mapped_column(default=False)
    builtin: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(default=0)
    field_schema: Mapped[list[Any]] = mapped_column(JSON, default=list)


class LinkType(Base):
    """A typed link between boxes, read forward on one box and backward on the other."""

    __tablename__ = "link_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(40), unique=True)
    forward_name: Mapped[str] = mapped_column(ShortText)
    backward_name: Mapped[str] = mapped_column(ShortText)
    description: Mapped[str] = mapped_column(Text, default="")
    role: Mapped[LinkRole] = mapped_column(str_enum(LinkRole))
    builtin: Mapped[bool] = mapped_column(default=False)
    position: Mapped[int] = mapped_column(default=0)
    field_schema: Mapped[list[Any]] = mapped_column(JSON, default=list)


class Box(Base):
    __tablename__ = "boxes"
    __table_args__ = (
        UniqueConstraint("id", "process_id"),  # target of the "same process" parent key
        ForeignKeyConstraint(
            ["parent_id", "process_id"],
            ["boxes.id", "boxes.process_id"],
            name="fk_boxes_parent_same_process",
        ),
        # A map box has a process (its section comes from there); a defect names its section.
        CheckConstraint(
            "(process_id IS NOT NULL AND section_id IS NULL)"
            " OR (process_id IS NULL AND section_id IS NOT NULL)",
            name="process_or_section",
        ),
        CheckConstraint(
            "process_id IS NOT NULL OR parent_id IS NULL", name="defects_have_no_parent"
        ),
        # One root (the box without a parent) per process map.
        Index(
            "uq_boxes_one_root_per_process",
            "process_id",
            unique=True,
            sqlite_where=text("parent_id IS NULL AND process_id IS NOT NULL"),
            mssql_where=text("parent_id IS NULL AND process_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Public, readable and fixed ("fm-level"): the box's link and the ?node= passed to dashboards.
    key: Mapped[str] = mapped_column(Unicode(MAX_KEY_LENGTH), unique=True)
    process_id: Mapped[int | None] = mapped_column(ForeignKey("processes.id"), index=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(default=0)  # among its siblings
    kind_id: Mapped[int] = mapped_column(ForeignKey("box_kinds.id"), index=True)
    name: Mapped[str] = mapped_column(LongName)
    body_md: Mapped[str] = mapped_column(Text, default="")
    main_url: Mapped[str | None] = mapped_column(Url)
    facts: Mapped[list[Any]] = mapped_column(JSON, default=list)  # [[key, value], ...]
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)  # per the kind's schema
    step_no: Mapped[str | None] = mapped_column(Unicode(20))  # "OP20"
    owner_person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"))
    reviewed_at: Mapped[date | None] = mapped_column(Date)
    rev: Mapped[int] = mapped_column(default=1)  # the latest revision's number
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012  (SQLAlchemy convention)

    kind: Mapped[BoxKind] = relationship()


class BoxLink(Base):
    __tablename__ = "box_links"
    __table_args__ = (
        UniqueConstraint("from_box_id", "to_box_id", "type_id"),
        CheckConstraint("from_box_id <> to_box_id", name="not_to_itself"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    from_box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"), index=True)
    to_box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"), index=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("link_types.id"), index=True)
    note_md: Mapped[str] = mapped_column(Text, default="")  # the "how"
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rev: Mapped[int] = mapped_column(default=1)

    type: Mapped[LinkType] = relationship()


class Control(Base):
    """How a failure mode is prevented or detected: its own record with a stable id."""

    __tablename__ = "controls"

    id: Mapped[int] = mapped_column(primary_key=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"), index=True)
    kind: Mapped[ControlKind] = mapped_column(str_enum(ControlKind))
    text: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(default=0)
    fields: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rev: Mapped[int] = mapped_column(default=1)


class ExternalLink(Base):
    """A dashboard, graph, calibration diagram or document elsewhere, of a box or a control.
    Part of its owner's content: editing one is a new revision of the box or control."""

    __tablename__ = "external_links"
    __table_args__ = (
        CheckConstraint(
            "(box_id IS NOT NULL AND control_id IS NULL)"
            " OR (box_id IS NULL AND control_id IS NOT NULL)",
            name="one_owner",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    box_id: Mapped[int | None] = mapped_column(ForeignKey("boxes.id"), index=True)
    control_id: Mapped[int | None] = mapped_column(ForeignKey("controls.id"), index=True)
    kind: Mapped[ExternalLinkKind] = mapped_column(str_enum(ExternalLinkKind))
    label: Mapped[str] = mapped_column(LongName)
    url: Mapped[str] = mapped_column(Url)
    pass_box_param: Mapped[bool] = mapped_column(default=False)  # adds ?node=<box key>
    position: Mapped[int] = mapped_column(default=0)


class Reference(Base):
    """A task or process change pointing at a box (DESIGN principle 5), with a role."""

    __tablename__ = "box_references"
    __table_args__ = (
        CheckConstraint(
            "(task_id IS NOT NULL AND change_id IS NULL)"
            " OR (task_id IS NULL AND change_id IS NOT NULL)",
            name="one_source",
        ),
        Index(
            "uq_box_references_task",
            "task_id",
            "box_id",
            "role",
            unique=True,
            sqlite_where=text("task_id IS NOT NULL"),
            mssql_where=text("task_id IS NOT NULL"),
        ),
        Index(
            "uq_box_references_change",
            "change_id",
            "box_id",
            "role",
            unique=True,
            sqlite_where=text("change_id IS NOT NULL"),
            mssql_where=text("change_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    change_id: Mapped[int | None] = mapped_column(ForeignKey("changes.id"), index=True)
    box_id: Mapped[int] = mapped_column(ForeignKey("boxes.id"), index=True)
    role: Mapped[ReferenceRole] = mapped_column(str_enum(ReferenceRole))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class Revision(Base):
    """One saved state of a box, link or control: its full content as JSON (DESIGN Versioning 1).
    Deletions are revisions too. Releases refer to (object, revision) pairs."""

    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("object_type", "object_id", "rev"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    object_type: Mapped[ObjectType] = mapped_column(str_enum(ObjectType))
    object_id: Mapped[int] = mapped_column(index=True)  # no FK: deleted objects keep revisions
    # The box whose history shows it: itself, a control's box, a link's "from" box.
    box_id: Mapped[int] = mapped_column(index=True)
    rev: Mapped[int]
    content: Mapped[dict[str, Any]] = mapped_column(JSON)
    deleted: Mapped[bool] = mapped_column(default=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Release(Base):
    """A released version (v1, v2, ...) of a process's FMEA and control plan: they share it
    (DESIGN Versioning 2-4). No approval step (D-081): it is current once made."""

    __tablename__ = "releases"
    __table_args__ = (
        UniqueConstraint("process_id", "number"),
        CheckConstraint("number >= 1", name="number_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    process_id: Mapped[int] = mapped_column(ForeignKey("processes.id"), index=True)
    number: Mapped[int]
    note: Mapped[str] = mapped_column(Text, default="")
    released_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    released_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class ReleaseItem(Base):
    """One frozen (object, revision) of a release: an old version is drawn from these alone."""

    __tablename__ = "release_items"

    release_id: Mapped[int] = mapped_column(ForeignKey("releases.id"), primary_key=True)
    object_type: Mapped[ObjectType] = mapped_column(str_enum(ObjectType), primary_key=True)
    object_id: Mapped[int] = mapped_column(primary_key=True)  # no FK: deleted objects stay
    rev: Mapped[int]
