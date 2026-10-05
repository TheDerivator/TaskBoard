"""Reference data use cases: the bootstrap document (who am I, departments, people, projects,
processes)."""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from taskboard.db.models import Department, Process, Section, Task
from taskboard.domain.access import Permission
from taskboard.domain.lifecycle import DEFAULT_VISIBLE_STATUSES, TaskStatus
from taskboard.identity.principal import Principal
from taskboard.identity.providers import IdentityProviders
from taskboard.schemas.auth import Me
from taskboard.schemas.reference import (
    Bootstrap,
    DepartmentOut,
    PersonOut,
    ProcessOut,
    StatusOut,
)
from taskboard.services.catalog import Catalog
from taskboard.services.projects import ProjectService
from taskboard.services.visibility import (
    can_view_anything,
    can_view_tasks,
    require_board_access,
    visible_tasks,
)

STATUSES = [
    StatusOut(value=s, label=s.label, shown_by_default=s in DEFAULT_VISIBLE_STATUSES)
    for s in TaskStatus
]


class ReferenceService:
    def __init__(self, session: Session, principal: Principal, today: date) -> None:
        self.session = session
        self.principal = principal
        self.today = today

    def bootstrap(self, providers: IdentityProviders) -> Bootstrap:
        me = Me.build(self.principal, providers)
        empty = Bootstrap(
            me=me,
            today=self.today,
            departments=[],
            people=[],
            projects=[],
            processes=[],
            statuses=STATUSES,
            task_total=0,
        )
        if self.principal.must_change_password or not can_view_anything(self.principal):
            return empty
        bootstrap = empty.model_copy(
            update={
                "departments": self.departments(),
                "people": self.people(),
                "processes": self.processes(),
            }
        )
        if can_view_tasks(self.principal):
            bootstrap.projects = ProjectService(self.session, self.principal).list()
            bootstrap.task_total = (
                self.session.scalar(
                    select(func.count()).select_from(
                        visible_tasks(select(Task), self.principal).subquery()
                    )
                )
                or 0
            )
        return bootstrap

    def processes(self) -> list[ProcessOut]:
        """The processes whose changes or map the caller may see, in display order."""
        changes = self.principal.reach(Permission.CHANGE_VIEW)
        knowledge = self.principal.reach(Permission.KNOWLEDGE_VIEW)
        rows = self.session.execute(
            select(Process, Section.department_id)
            .join(Section, Section.id == Process.section_id)
            .order_by(Process.position, Process.id)
        )
        return [
            ProcessOut(
                id=process.id,
                code=process.code,
                name=process.name,
                section_id=process.section_id,
                department_id=department_id,
                position=process.position,
            )
            for process, department_id in rows
            if changes.includes(process.section_id) or knowledge.includes(process.section_id)
        ]

    def departments(self) -> list[DepartmentOut]:
        query = (
            select(Department)
            .options(selectinload(Department.sections))
            .order_by(Department.position, Department.id)
        )
        return [DepartmentOut.model_validate(d) for d in self.session.scalars(query)]

    def people(self) -> list[PersonOut]:
        if not require_board_access(self.principal):
            return []
        catalog = Catalog.load(self.session)
        return [
            PersonOut(
                id=p.id,
                code=p.code,
                name=p.name,
                color=p.color,
                section_id=p.section_id,
                department_id=catalog.department_of(p.section_id),
                active=p.active,
            )
            for p in sorted(catalog.people.values(), key=lambda p: p.name)
        ]
