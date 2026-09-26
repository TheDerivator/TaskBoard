"""People on the board (task leads and helpers). Not the same as login accounts (users)."""

from sqlalchemy import ForeignKey, Index, Unicode, text
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from taskboard.db.base import Base, Color, Email, Name, normalize_email
from taskboard.db.models.org import Section


class Person(Base):
    __tablename__ = "people"
    __table_args__ = (
        # Filtered unique index: MS SQL's UNIQUE would allow only one NULL email.
        Index(
            "uq_people_email",
            "email",
            unique=True,
            sqlite_where=text("email IS NOT NULL"),
            mssql_where=text("email IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(Unicode(8), unique=True)  # initials, e.g. "AC"
    name: Mapped[str] = mapped_column(Name)
    color: Mapped[str] = mapped_column(Color)  # avatar background, "#2D5BA8"
    email: Mapped[str | None] = mapped_column(Email)  # stored lowercase
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    active: Mapped[bool] = mapped_column(default=True)

    section: Mapped[Section] = relationship()

    @validates("email")
    def _normalize_email(self, _key: str, value: str | None) -> str | None:
        return normalize_email(value)
