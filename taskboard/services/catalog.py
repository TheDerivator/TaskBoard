"""Reference data loaded once per request: sections, people, projects and their outlines.

Small tables, read whole: services use the catalog to validate ids and to render node numbers
and paths without extra queries.
"""

from dataclasses import dataclass
from typing import Self

from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.models import Person, Project, ProjectNode, Section
from taskboard.domain.errors import NotFoundError, RuleViolationError
from taskboard.domain.outline import Outline, TreeNode


@dataclass
class ProjectTree:
    project: Project
    nodes: dict[int, ProjectNode]
    outline: Outline[int]

    def number(self, node_id: int | None) -> str | None:
        return None if node_id is None else self.outline.number(node_id)

    def path(self, node_id: int | None) -> list[str]:
        """Node names from the top-level section down to `node_id` (empty for top level)."""
        if node_id is None:
            return []
        chain = [*self.outline.ancestors(node_id), node_id]
        return [self.nodes[n].name for n in chain]

    def require_node(self, node_id: int | None) -> None:
        if node_id is not None and node_id not in self.nodes:
            raise RuleViolationError(
                f"node {node_id} does not belong to project {self.project.key}"
            )


class Catalog:
    def __init__(
        self,
        sections: dict[int, Section],
        people: dict[int, Person],
        projects: dict[int, ProjectTree],
    ) -> None:
        self.sections = sections
        self.people = people
        self.projects = projects

    @classmethod
    def load(cls, session: Session) -> Self:
        sections = {s.id: s for s in session.scalars(select(Section))}
        people = {p.id: p for p in session.scalars(select(Person))}
        nodes_by_project: dict[int, list[ProjectNode]] = {}
        for node in session.scalars(select(ProjectNode)):
            nodes_by_project.setdefault(node.project_id, []).append(node)
        projects: dict[int, ProjectTree] = {}
        for project in session.scalars(select(Project).order_by(Project.position, Project.id)):
            nodes = nodes_by_project.get(project.id, [])
            projects[project.id] = ProjectTree(
                project=project,
                nodes={n.id: n for n in nodes},
                outline=Outline(TreeNode(n.id, n.parent_id, n.position) for n in nodes),
            )
        return cls(sections, people, projects)

    def department_of(self, section_id: int) -> int:
        return self.sections[section_id].department_id

    def section_ids_of_department(self, department_id: int) -> set[int]:
        return {s.id for s in self.sections.values() if s.department_id == department_id}

    def require_section(self, section_id: int) -> Section:
        if section_id not in self.sections:
            raise RuleViolationError(f"unknown section {section_id}")
        return self.sections[section_id]

    def require_person(self, person_id: int) -> Person:
        if person_id not in self.people:
            raise RuleViolationError(f"unknown person {person_id}")
        return self.people[person_id]

    def tree(self, project_id: int) -> ProjectTree:
        if project_id not in self.projects:
            raise NotFoundError(f"unknown project {project_id}")
        return self.projects[project_id]

    def tree_by_key(self, key: str) -> ProjectTree:
        for tree in self.projects.values():
            if tree.project.key == key.upper():
                return tree
        raise NotFoundError(f"unknown project {key}")
