"""Reference data shapes: departments and sections, people, lifecycle states, bootstrap."""

from pydantic import BaseModel, ConfigDict

from taskboard.domain.lifecycle import TaskStatus
from taskboard.schemas.auth import Me
from taskboard.schemas.projects import ProjectOut


class SectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    department_id: int
    name: str
    position: int


class DepartmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    position: int
    sections: list[SectionOut]


class PersonOut(BaseModel):
    id: int
    code: str
    name: str
    color: str
    section_id: int
    department_id: int
    active: bool


class StatusOut(BaseModel):
    value: TaskStatus
    label: str
    shown_by_default: bool


class Bootstrap(BaseModel):
    """Everything the frontend needs to start. Empty lists when the caller may view nothing."""

    me: Me
    departments: list[DepartmentOut]
    people: list[PersonOut]
    projects: list[ProjectOut]
    statuses: list[StatusOut]
    task_total: int  # all tasks the caller can see
