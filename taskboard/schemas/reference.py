"""Reference data shapes: departments and sections, people, lifecycle states, bootstrap."""

from datetime import date

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


class ProcessOut(BaseModel):
    """A process (e.g. Continuous casting) of a department, owned by one of its sections."""

    id: int
    code: str
    name: str
    section_id: int
    department_id: int
    position: int


class StatusOut(BaseModel):
    value: TaskStatus
    label: str
    shown_by_default: bool


class Bootstrap(BaseModel):
    """Everything the frontend needs to start. Empty lists when the caller may view nothing."""

    me: Me
    today: date  # the server's date: periods and states are judged by it, in browser and server
    departments: list[DepartmentOut]
    people: list[PersonOut]
    projects: list[ProjectOut]
    processes: list[ProcessOut]  # those the caller may see in process changes or knowledge
    statuses: list[StatusOut]
    task_total: int  # all tasks the caller can see
