"""Project use cases: list projects with counts, unfold an outline, edit projects and their trees.

Counts only include tasks the caller can see and, unless asked, no archived tasks. A node's count
includes everything below it (DESIGN rule 7). Editing structure needs `project.manage`.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from taskboard.db.models import Event, Placement, Project, ProjectNode, Task
from taskboard.domain.access import Permission
from taskboard.domain.errors import ConflictError, NotFoundError, RuleViolationError
from taskboard.domain.events import EventKind
from taskboard.domain.lifecycle import TaskStatus
from taskboard.domain.outline import subtree_counts
from taskboard.identity.principal import Principal
from taskboard.schemas.projects import (
    Crumb,
    NodeCreate,
    NodeOut,
    NodeUpdate,
    OutlineSection,
    ProjectCreate,
    ProjectOut,
    ProjectOutline,
    ProjectUpdate,
)
from taskboard.schemas.tasks import TaskSummary
from taskboard.services.catalog import Catalog, ProjectTree
from taskboard.services.tasks import summarize, with_card_data
from taskboard.services.visibility import ensure_usable, visible_tasks

type DirectCounts = dict[
    tuple[int, int | None], int
]  # (project, node or None) → tasks placed there


class ProjectService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal

    # ------------------------------------------------------------------ queries

    def list(self, *, include_archived: bool = False) -> list[ProjectOut]:
        catalog = Catalog.load(self.session)
        direct = self._direct_counts(include_archived)
        return [self._project_out(tree, direct) for tree in catalog.projects.values()]

    def outline(
        self, key: str, *, node_id: int | None = None, include_archived: bool = False
    ) -> ProjectOutline:
        catalog = Catalog.load(self.session)
        tree = catalog.tree_by_key(key)
        if node_id is not None and node_id not in tree.nodes:
            raise NotFoundError(f"no node {node_id} in project {key}")
        project = self._project_out(tree, self._direct_counts(include_archived))
        nodes = {n.id: n for n in project.nodes}

        query = visible_tasks(
            select(Task).join(Placement).where(Placement.project_id == tree.project.id),
            self.principal,
        )
        if not include_archived:
            query = query.where(Task.status != TaskStatus.ARCHIVED)
        by_node: dict[int | None, list[TaskSummary]] = {}
        for task in self.session.scalars(with_card_data(query.order_by(Task.rank))):
            placement = next(p for p in task.placements if p.project_id == tree.project.id)
            by_node.setdefault(placement.node_id, []).append(summarize(task, catalog))

        in_scope = tree.outline.subtree(node_id) if node_id is not None else set(tree.nodes)
        sections = [
            OutlineSection(node=nodes[n], tasks=by_node.get(n, []))
            for n in tree.outline.preorder()
            if n in in_scope
        ]
        top_level = by_node.get(None, []) if node_id is None else []
        shown = sorted([*top_level, *(t for s in sections for t in s.tasks)], key=lambda t: t.rank)
        open_tasks = [t for t in shown if t.status is not TaskStatus.ARCHIVED]
        return ProjectOutline(
            project=project,
            node=nodes[node_id] if node_id is not None else None,
            breadcrumb=self._breadcrumb(tree, node_id),
            top_level_tasks=top_level,
            sections=sections,
            open_count=len(open_tasks),
            lead_ids=list(dict.fromkeys(t.lead_id for t in open_tasks)),
        )

    def _direct_counts(self, include_archived: bool) -> DirectCounts:
        query = visible_tasks(
            select(Placement.project_id, Placement.node_id, func.count())
            .join(Task, Task.id == Placement.task_id)
            .group_by(Placement.project_id, Placement.node_id),
            self.principal,
        )
        if not include_archived:
            query = query.where(Task.status != TaskStatus.ARCHIVED)
        return {(project, node): count for project, node, count in self.session.execute(query)}

    @staticmethod
    def _project_out(tree: ProjectTree, direct: DirectCounts) -> ProjectOut:
        pid = tree.project.id
        per_node = {node: n for (p, node), n in direct.items() if p == pid and node is not None}
        totals = subtree_counts(tree.outline, per_node)
        return ProjectOut(
            id=pid,
            key=tree.project.key,
            name=tree.project.name,
            color=tree.project.color,
            position=tree.project.position,
            archived=tree.project.archived,
            count=sum(n for (p, _), n in direct.items() if p == pid),
            nodes=[
                NodeOut(
                    id=n,
                    parent_id=tree.nodes[n].parent_id,
                    position=tree.nodes[n].position,
                    name=tree.nodes[n].name,
                    number=tree.outline.number(n),
                    depth=tree.outline.depth(n),
                    count=totals[n],
                )
                for n in tree.outline.preorder()
            ],
        )

    @staticmethod
    def _breadcrumb(tree: ProjectTree, node_id: int | None) -> list[Crumb]:
        crumbs = [Crumb(node_id=None, label=tree.project.name)]
        if node_id is not None:
            for n in [*tree.outline.ancestors(node_id), node_id]:
                crumbs.append(
                    Crumb(node_id=n, label=f"{tree.outline.number(n)} {tree.nodes[n].name}")
                )
        return crumbs

    # ------------------------------------------------------------------ project commands

    def _require_manage(self) -> None:
        ensure_usable(self.principal)
        self.principal.require(Permission.PROJECT_MANAGE)

    def _project_by_key(self, key: str) -> Project:
        project = self.session.scalars(
            select(Project).where(Project.key == key.upper())
        ).one_or_none()
        if project is None:
            raise NotFoundError(f"unknown project {key}")
        return project

    def _result(self, project_id: int) -> ProjectOut:
        self.session.commit()
        catalog = Catalog.load(self.session)
        return self._project_out(catalog.tree(project_id), self._direct_counts(False))

    def create(self, data: ProjectCreate) -> ProjectOut:
        self._require_manage()
        if self.session.scalar(select(Project.id).where(Project.key == data.key)) is not None:
            raise ConflictError(f"a project with key {data.key} already exists")
        last = self.session.scalar(select(func.max(Project.position))) or 0
        project = Project(key=data.key, name=data.name, color=data.color, position=last + 1)
        self.session.add(project)
        self.session.flush()
        return self._result(project.id)

    def update(self, key: str, data: ProjectUpdate) -> ProjectOut:
        self._require_manage()
        project = self._project_by_key(key)
        for field in ("name", "color", "position", "archived"):
            value = getattr(data, field)
            if value is not None:
                setattr(project, field, value)
        return self._result(project.id)

    def delete(self, key: str) -> None:
        """Remove a project, its sections and all placements in it. The tasks stay."""
        self._require_manage()
        project = self._project_by_key(key)
        self.session.execute(delete(Placement).where(Placement.project_id == project.id))
        self.session.execute(
            update(ProjectNode).where(ProjectNode.project_id == project.id).values(parent_id=None)
        )
        self.session.execute(delete(ProjectNode).where(ProjectNode.project_id == project.id))
        self.session.delete(project)
        self.session.commit()

    # ------------------------------------------------------------------ node commands

    def add_node(self, key: str, data: NodeCreate) -> ProjectOut:
        self._require_manage()
        project = self._project_by_key(key)
        tree = Catalog.load(self.session).tree(project.id)
        tree.require_node(data.parent_id)
        siblings = tree.outline.children(data.parent_id)
        last = max((tree.nodes[s].position for s in siblings), default=0)
        self.session.add(
            ProjectNode(
                project_id=project.id, parent_id=data.parent_id, position=last + 1, name=data.name
            )
        )
        return self._result(project.id)

    def update_node(self, key: str, node_id: int, data: NodeUpdate) -> ProjectOut:
        self._require_manage()
        project = self._project_by_key(key)
        tree = Catalog.load(self.session).tree(project.id)
        if node_id not in tree.nodes:
            raise NotFoundError(f"no node {node_id} in project {key}")
        node = tree.nodes[node_id]
        if data.name is not None:
            node.name = data.name
        if data.moves:
            parent = data.parent_id if "parent_id" in data.model_fields_set else node.parent_id
            tree.require_node(parent)
            if tree.outline.would_create_cycle(node_id, parent):
                raise RuleViolationError("a section cannot move inside itself")
            old_siblings = [s for s in tree.outline.children(node.parent_id) if s != node_id]
            new_siblings = [s for s in tree.outline.children(parent) if s != node_id]
            index = len(new_siblings) if data.index is None else min(data.index, len(new_siblings))
            new_siblings.insert(index, node_id)
            node.parent_id = parent
            self._renumber(tree, old_siblings)
            self._renumber(tree, new_siblings)
        return self._result(project.id)

    def delete_node(self, key: str, node_id: int) -> ProjectOut:
        """Delete a node and its subtree; tasks placed there move up to the node's parent."""
        self._require_manage()
        project = self._project_by_key(key)
        tree = Catalog.load(self.session).tree(project.id)
        if node_id not in tree.nodes:
            raise NotFoundError(f"no node {node_id} in project {key}")
        parent = tree.nodes[node_id].parent_id
        subtree = tree.outline.subtree(node_id)
        moved = self.session.execute(
            select(Placement.task_id, Placement.node_id).where(Placement.node_id.in_(subtree))
        ).all()
        for task_id, from_node in moved:
            self.session.add(
                Event(
                    task_id=task_id,
                    actor_user_id=self.principal.user_id,
                    api_token_id=self.principal.token_id,
                    kind=EventKind.PLACEMENT_MOVED,
                    data={"project": project.id, "from": from_node, "to": parent},
                )
            )
        self.session.execute(
            update(Placement).where(Placement.node_id.in_(subtree)).values(node_id=parent)
        )
        for doomed in reversed(tree.outline.preorder()):  # children before parents
            if doomed in subtree:
                self.session.execute(delete(ProjectNode).where(ProjectNode.id == doomed))
        self._renumber(tree, [s for s in tree.outline.children(parent) if s != node_id])
        return self._result(project.id)

    @staticmethod
    def _renumber(tree: ProjectTree, ordered: list[int]) -> None:
        for position, node_id in enumerate(ordered, start=1):
            tree.nodes[node_id].position = position
