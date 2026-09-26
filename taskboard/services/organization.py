"""Organization administration: departments, sections and people (needs `people.manage`).

Departments and sections are only deleted when nothing depends on them any more. People are
never deleted (tasks and history refer to them); they are deactivated instead.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import Department, Person, RoleAssignment, Section, Task, User
from taskboard.domain.access import Permission
from taskboard.domain.errors import ConflictError, NotFoundError, RuleViolationError
from taskboard.identity.principal import Principal
from taskboard.schemas.admin import (
    DepartmentIn,
    DepartmentUpdate,
    PersonAdminOut,
    PersonIn,
    PersonUpdate,
    SectionIn,
    SectionUpdate,
)
from taskboard.schemas.reference import DepartmentOut
from taskboard.services import audit
from taskboard.services.visibility import ensure_usable


class OrganizationService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        ensure_usable(principal)
        principal.require(Permission.PEOPLE_MANAGE)

    def _record(self, action: str, target_type: str, target_id: object, **details: object) -> None:
        audit.record(
            self.session,
            action,
            actor_user_id=self.principal.user_id,
            target_type=target_type,
            target_id=target_id,
            **details,
        )

    def _count(self, *where: object) -> int:
        return self.session.scalar(select(func.count()).where(*where)) or 0  # type: ignore[arg-type]

    # ------------------------------------------------------------------ departments

    def _department(self, department_id: int) -> Department:
        department = self.session.get(Department, department_id)
        if department is None:
            raise NotFoundError(f"no department {department_id}")
        return department

    def _department_out(self, department: Department) -> DepartmentOut:
        self.session.refresh(department)
        return DepartmentOut.model_validate(department)

    def create_department(self, data: DepartmentIn) -> DepartmentOut:
        if self.session.scalar(select(Department.id).where(Department.code == data.code)):
            raise ConflictError(f"a department with code {data.code} exists")
        last = self.session.scalar(select(func.max(Department.position))) or 0
        department = Department(code=data.code, name=data.name, position=last + 1)
        self.session.add(department)
        self.session.flush()
        self._record("department.created", "department", department.id, code=department.code)
        self.session.commit()
        return self._department_out(department)

    def update_department(self, department_id: int, data: DepartmentUpdate) -> DepartmentOut:
        department = self._department(department_id)
        if data.code is not None and data.code != department.code:
            if self.session.scalar(select(Department.id).where(Department.code == data.code)):
                raise ConflictError(f"a department with code {data.code} exists")
            department.code = data.code
        if data.name is not None:
            department.name = data.name
        if data.position is not None:
            department.position = data.position
        self._record(
            "department.updated", "department", department.id, **data.model_dump(exclude_none=True)
        )
        self.session.commit()
        return self._department_out(department)

    def delete_department(self, department_id: int) -> None:
        department = self._department(department_id)
        if self._count(Section.department_id == department.id):
            raise ConflictError("delete or move its sections first")
        if self._count(RoleAssignment.department_id == department.id):
            raise ConflictError("access rights are granted on this department; remove them first")
        self._record("department.deleted", "department", department.id, code=department.code)
        self.session.delete(department)
        self.session.commit()

    # ------------------------------------------------------------------ sections

    def _section(self, section_id: int) -> Section:
        section = self.session.get(Section, section_id)
        if section is None:
            raise NotFoundError(f"no section {section_id}")
        return section

    def _check_section_name(self, department_id: int, name: str, own_id: int | None = None) -> None:
        clash = self.session.scalar(
            select(Section.id).where(Section.department_id == department_id, Section.name == name)
        )
        if clash is not None and clash != own_id:
            raise ConflictError(f"the department already has a section {name}")

    def create_section(self, data: SectionIn) -> DepartmentOut:
        department = self._department(data.department_id)
        self._check_section_name(department.id, data.name)
        last = self.session.scalar(
            select(func.max(Section.position)).where(Section.department_id == department.id)
        )
        section = Section(department_id=department.id, name=data.name, position=(last or 0) + 1)
        self.session.add(section)
        self.session.flush()
        self._record(
            "section.created", "section", section.id, name=section.name, department=department.code
        )
        self.session.commit()
        return self._department_out(department)

    def update_section(self, section_id: int, data: SectionUpdate) -> DepartmentOut:
        section = self._section(section_id)
        if data.name is not None:
            self._check_section_name(section.department_id, data.name, section.id)
            section.name = data.name
        if data.position is not None:
            section.position = data.position
        self._record("section.updated", "section", section.id, **data.model_dump(exclude_none=True))
        self.session.commit()
        return self._department_out(section.department)

    def delete_section(self, section_id: int) -> DepartmentOut:
        section = self._section(section_id)
        usage = {
            "tasks": self._count(Task.section_id == section.id),
            "people": self._count(Person.section_id == section.id),
            "access rights": self._count(RoleAssignment.section_id == section.id),
        }
        blocking = [f"{n} {what}" for what, n in usage.items() if n]
        if blocking:
            raise ConflictError(f"the section is still used by {', '.join(blocking)}")
        department = section.department
        self._record("section.deleted", "section", section.id, name=section.name)
        self.session.delete(section)
        self.session.commit()
        return self._department_out(department)

    # ------------------------------------------------------------------ people

    def _person_out(self, person: Person) -> PersonAdminOut:
        return PersonAdminOut(
            id=person.id,
            code=person.code,
            name=person.name,
            color=person.color,
            email=person.email,
            section_id=person.section_id,
            department_id=person.section.department_id,
            active=person.active,
            user_id=self.session.scalar(select(User.id).where(User.person_id == person.id)),
        )

    def list_people(self) -> list[PersonAdminOut]:
        return [
            self._person_out(p) for p in self.session.scalars(select(Person).order_by(Person.name))
        ]

    def _check_person_code(self, code: str, own_id: int | None = None) -> None:
        clash = self.session.scalar(select(Person.id).where(Person.code == code))
        if clash is not None and clash != own_id:
            raise ConflictError(f"the code {code} is already used")

    def create_person(self, data: PersonIn) -> PersonAdminOut:
        self._section(data.section_id)
        self._check_person_code(data.code)
        person = Person(**data.model_dump())
        self.session.add(person)
        self.session.flush()
        self._record("person.created", "person", person.id, code=person.code, name=person.name)
        self.session.commit()
        return self._person_out(person)

    def update_person(self, person_id: int, data: PersonUpdate) -> PersonAdminOut:
        person = self.session.get(Person, person_id)
        if person is None:
            raise NotFoundError(f"no person {person_id}")
        sent = data.model_fields_set
        if data.code is not None:
            self._check_person_code(data.code, person.id)
            person.code = data.code
        if data.section_id is not None:
            self._section(data.section_id)
            person.section_id = data.section_id
        for field in ("name", "color", "active"):
            value = getattr(data, field)
            if value is not None:
                setattr(person, field, value)
        if "email" in sent:
            person.email = data.email
        # Inactive people can no longer be chosen, so whoever still leads tasks hands them over
        # first. (Helping on tasks is fine: the name simply stays visible there.)
        if data.active is False and (leading := self._count(Task.lead_person_id == person.id)):
            raise RuleViolationError(
                f"{person.name} still leads {leading} task(s); give them another lead first"
            )
        self._record("person.updated", "person", person.id, **data.model_dump(exclude_unset=True))
        self.session.commit()
        return self._person_out(person)
