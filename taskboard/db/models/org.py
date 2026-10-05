"""Organization tables: departments, their sections (the scopes for access rights) and processes."""

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, Code, Name, ShortText


class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Code, unique=True)  # e.g. "STL", "R&D"
    name: Mapped[str] = mapped_column(ShortText)
    position: Mapped[int] = mapped_column(default=0)

    sections: Mapped[list[Section]] = relationship(
        back_populates="department", order_by="Section.position"
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (UniqueConstraint("department_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    department_id: Mapped[int] = mapped_column(ForeignKey("departments.id"), index=True)
    name: Mapped[str] = mapped_column(ShortText)  # e.g. "Quality"
    position: Mapped[int] = mapped_column(default=0)

    department: Mapped[Department] = relationship(back_populates="sections")


class Process(Base):
    """A production process (e.g. STL › Continuous casting): owns process changes and a map.

    It belongs to a department through its owning section, which also decides who may see and
    edit its changes and its map (section-scoped rights, like a task's section).
    """

    __tablename__ = "processes"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Short and unique everywhere ("CC"): it prefixes change keys (CC-31) and appears in links.
    # Stored uppercase; never changed once created.
    code: Mapped[str] = mapped_column(Code, unique=True)
    name: Mapped[str] = mapped_column(Name)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    position: Mapped[int] = mapped_column(default=0)

    section: Mapped[Section] = relationship()
