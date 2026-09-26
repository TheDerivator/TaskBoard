"""Projects and their node trees (sections and subsections, any depth)."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from taskboard.db.base import Base, Code, Color, Name


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Code, unique=True)  # short code, e.g. "ASQ"
    name: Mapped[str] = mapped_column(Name)
    color: Mapped[str] = mapped_column(Color)
    position: Mapped[int] = mapped_column(default=0)
    archived: Mapped[bool] = mapped_column(default=False)

    # No ORM delete cascade: a self-referencing tree must be deleted leaves-first, which the
    # project service does explicitly.
    nodes: Mapped[list[ProjectNode]] = relationship(back_populates="project")


class ProjectNode(Base):
    """A section of a project. Display numbers (2.2.1) are derived, see domain/outline.py."""

    __tablename__ = "project_nodes"
    __table_args__ = (
        # Target of composite FKs that force "same project" at the database level.
        UniqueConstraint("id", "project_id"),
        # A parent must belong to the same project. No ON DELETE CASCADE (MS SQL forbids it on
        # self-references); services delete subtrees explicitly.
        ForeignKeyConstraint(
            ["parent_id", "project_id"],
            ["project_nodes.id", "project_nodes.project_id"],
            name="fk_project_nodes_parent_same_project",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_id: Mapped[int | None] = mapped_column(index=True)
    position: Mapped[int] = mapped_column(default=0)  # order among siblings
    name: Mapped[str] = mapped_column(Name)

    project: Mapped[Project] = relationship(back_populates="nodes")
