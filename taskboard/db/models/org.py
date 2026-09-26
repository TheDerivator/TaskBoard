"""Organization tables: departments and their sections (the scopes for access rights)."""

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, Code, ShortText


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
