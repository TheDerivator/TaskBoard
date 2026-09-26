"""Reference data use cases: the bootstrap document (who am I, departments, people, projects)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from taskboard.db.models import Department, Task
from taskboard.domain.lifecycle import DEFAULT_VISIBLE_STATUSES, TaskStatus
from taskboard.identity.principal import Principal
from taskboard.identity.providers import IdentityProviders
from taskboard.schemas.auth import Me
from taskboard.schemas.reference import Bootstrap, DepartmentOut, PersonOut, StatusOut
from taskboard.services.catalog import Catalog
from taskboard.services.projects import ProjectService
from taskboard.services.visibility import can_view_anything, require_board_access, visible_tasks

STATUSES = [
    StatusOut(value=s, label=s.label, shown_by_default=s in DEFAULT_VISIBLE_STATUSES)
    for s in TaskStatus
]


class ReferenceService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    def bootstrap(self, providers: IdentityProviders) -> Bootstrap:
        me = Me.build(self.principal, providers)
        if self.principal.must_change_password or not can_view_anything(self.principal):
            return Bootstrap(
                me=me, departments=[], people=[], projects=[], statuses=STATUSES, task_total=0
            )
        return Bootstrap(
            me=me,
            departments=self.departments(),
            people=self.people(),
            projects=ProjectService(self.session, self.principal).list(),
            statuses=STATUSES,
            task_total=self.session.scalar(
                select(func.count()).select_from(
                    visible_tasks(select(Task), self.principal).subquery()
                )
            )
            or 0,
        )

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
