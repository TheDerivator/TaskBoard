"""Task shapes: list filters, summaries and details, create/update/move commands, placements."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.ranking import Where

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Description = Annotated[str, StringConstraints(max_length=20_000)]


class PersonRole(StrEnum):
    LEAD = "lead"
    HELPER = "helper"
    ANY = "any"


class TaskFilter(BaseModel):
    """Filters only hide tasks; they never change ranks (DESIGN rule 2)."""

    q: str | None = None  # case-insensitive, title + description
    statuses: list[TaskStatus] | None = None  # None = every status
    department_id: int | None = None
    section_id: int | None = None
    project_id: int | None = None
    node_id: int | None = None  # the node and everything below it
    person_id: int | None = None
    person_role: PersonRole = PersonRole.ANY


class PlacementOut(BaseModel):
    project_id: int
    node_id: int | None
    number: str | None  # outline number of the node, e.g. "2.2.1"; None = top level
    path: list[
        str
    ]  # node names from the top-level section down, e.g. ["Line 2 defects", "Root cause"]


class TaskSummary(BaseModel):
    key: str  # public short id, e.g. "K7Q2MX"
    ref: str  # how people write it, e.g. "T-K7Q2MX"
    url: str  # permalink, e.g. "/t/K7Q2MX"
    rank: int  # global, team-wide
    title: str
    description: str
    status: TaskStatus
    lead_id: int
    helper_ids: list[int]
    section_id: int
    department_id: int
    placements: list[PlacementOut]
    version: int


class TaskList(BaseModel):
    tasks: list[TaskSummary]
    total: int  # tasks the caller can see, before filters


class TaskPermissions(BaseModel):
    edit: bool
    comment: bool
    delete: bool


class TaskDetail(TaskSummary):
    created_at: datetime
    updated_at: datetime
    rank_total: int  # "Rank 01 of 11"
    post_count: int  # conversation posts (for the tab badge)
    permissions: TaskPermissions


class PlacementIn(BaseModel):
    project_id: int
    node_id: int | None = None


class TaskCreate(BaseModel):
    title: Title
    description: Description = ""
    status: TaskStatus = TaskStatus.IDEA
    lead_id: int
    helper_ids: list[int] = []
    section_id: int
    placements: list[PlacementIn] = []


class TaskUpdate(BaseModel):
    """Only the fields present are changed. `version` must match (optimistic locking)."""

    version: int
    title: Title | None = None
    description: Description | None = None
    status: TaskStatus | None = None
    lead_id: int | None = None
    helper_ids: list[int] | None = None
    section_id: int | None = None


class TaskMove(BaseModel):
    """Place the task directly before or after another task in the team-wide ranking."""

    target: str  # key of the task it was dropped on
    where: Where


class PlacementMove(BaseModel):
    node_id: int | None = None
