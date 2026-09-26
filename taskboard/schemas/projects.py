"""Project shapes: projects with their node trees and counts, outlines, and edit commands."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from taskboard.schemas.tasks import TaskSummary

ProjectKey = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{2,10}$")
]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class NodeOut(BaseModel):
    id: int
    parent_id: int | None
    position: int
    name: str
    number: str  # "2.2.1", derived from positions
    depth: int  # 1 = top-level section
    count: int  # visible tasks placed on this node or below it


class ProjectOut(BaseModel):
    id: int
    key: str
    name: str
    color: str
    position: int
    archived: bool
    count: int  # visible tasks placed anywhere in the project
    nodes: list[NodeOut]  # in outline order


class OutlineSection(BaseModel):
    node: NodeOut
    tasks: list[TaskSummary]  # placed directly on this node, in rank order


class Crumb(BaseModel):
    node_id: int | None  # None = the project itself
    label: str


class ProjectOutline(BaseModel):
    """A project (or one node's subtree) unfolded as a numbered outline (DESIGN rule 7)."""

    project: ProjectOut
    node: NodeOut | None
    breadcrumb: list[Crumb]
    top_level_tasks: list[TaskSummary]  # placed on the project itself (only for the whole project)
    sections: list[OutlineSection]  # the subtree in outline order
    open_count: int  # non-archived tasks in view
    lead_ids: list[int]  # distinct leads of those tasks, in rank order


class ProjectCreate(BaseModel):
    key: ProjectKey
    name: Name
    color: Color


class ProjectUpdate(BaseModel):
    name: Name | None = None
    color: Color | None = None
    position: int | None = None
    archived: bool | None = None


class NodeCreate(BaseModel):
    name: Name
    parent_id: int | None = None  # None = new top-level section; added as the last child


class NodeUpdate(BaseModel):
    """Rename and/or move. Sending `parent_id` (null = top level) and/or `index` moves the node:
    it becomes child number `index` (0-based; default last) of that parent."""

    name: Name | None = None
    parent_id: int | None = None
    index: int | None = Field(default=None, ge=0)

    @property
    def moves(self) -> bool:
        return bool({"parent_id", "index"} & self.model_fields_set)
