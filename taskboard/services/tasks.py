"""Task use cases: list (filtered, visible only), read, create, edit, re-rank, delete, placements.

Every change writes the automatic events the conversation shows (lifecycle, people, section,
placements). Rank changes take the ranking lock and shift a contiguous range in one UPDATE; they
do not change the task's `version`, so reordering never conflicts with someone editing a task.
"""

from typing import Any

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from taskboard.db.base import utcnow
from taskboard.db.models import Attachment, Event, Placement, Post, Task, TaskHelper
from taskboard.db.session import TASK_RANKING_LOCK, acquire_lock
from taskboard.db.text import contains_ci
from taskboard.domain.access import Permission
from taskboard.domain.errors import (
    ConflictError,
    NotFoundError,
    RuleViolationError,
    StaleVersionError,
)
from taskboard.domain.events import EventKind
from taskboard.domain.ranking import plan_move
from taskboard.domain.task_keys import (
    InvalidTaskKeyError,
    display_key,
    generate_unique_key,
    normalize_key,
)
from taskboard.identity.principal import Principal
from taskboard.schemas.tasks import (
    PersonRole,
    PlacementIn,
    PlacementMove,
    PlacementOut,
    TaskCreate,
    TaskDetail,
    TaskFilter,
    TaskList,
    TaskMove,
    TaskPermissions,
    TaskSummary,
    TaskUpdate,
)
from taskboard.services.attachments import AttachmentStore
from taskboard.services.catalog import Catalog
from taskboard.services.visibility import visible_tasks


def permalink(key: str) -> str:
    return f"/t/{key}"


def summarize(task: Task, catalog: Catalog) -> TaskSummary:
    """The list/card representation of a task. Needs `helpers` and `placements` loaded."""
    placements = sorted(
        task.placements, key=lambda p: (catalog.tree(p.project_id).project.position, p.project_id)
    )
    return TaskSummary(
        key=task.key,
        ref=display_key(task.key),
        url=permalink(task.key),
        rank=task.rank,
        title=task.title,
        description=task.description,
        status=task.status,
        lead_id=task.lead_person_id,
        helper_ids=sorted(
            (h.person_id for h in task.helpers), key=lambda pid: catalog.people[pid].name
        ),
        section_id=task.section_id,
        department_id=catalog.department_of(task.section_id),
        placements=[
            PlacementOut(
                project_id=p.project_id,
                node_id=p.node_id,
                number=catalog.tree(p.project_id).number(p.node_id),
                path=catalog.tree(p.project_id).path(p.node_id),
            )
            for p in placements
        ],
        version=task.version,
    )


def with_card_data[*Ts](query: Select[*Ts]) -> Select[*Ts]:
    """Eager-load what `summarize` needs (two extra queries for any number of tasks)."""
    return query.options(selectinload(Task.helpers), selectinload(Task.placements))


class TaskService:
    def __init__(
        self, session: Session, principal: Principal, store: AttachmentStore | None = None
    ) -> None:
        self.session = session
        self.principal = principal
        self.store = store  # to remove the files of deleted tasks

    # ------------------------------------------------------------------ queries

    def list(self, filters: TaskFilter) -> TaskList:
        catalog = Catalog.load(self.session)
        visible = visible_tasks(select(Task), self.principal)
        total = self.session.scalar(select(func.count()).select_from(visible.subquery())) or 0
        query = with_card_data(self._filtered(visible, filters, catalog).order_by(Task.rank))
        tasks = self.session.scalars(query).all()
        return TaskList(tasks=[summarize(t, catalog) for t in tasks], total=total)

    def get(self, key: str) -> TaskDetail:
        return self._detail(self.find(key), Catalog.load(self.session))

    def _filtered(self, query: Select[Task], f: TaskFilter, catalog: Catalog) -> Select[Task]:
        if f.q and f.q.strip():
            needle = f.q.strip()
            query = query.where(
                or_(contains_ci(Task.title, needle), contains_ci(Task.description, needle))
            )
        if f.statuses is not None:
            query = query.where(Task.status.in_(f.statuses))
        if f.department_id is not None:
            query = query.where(
                Task.section_id.in_(catalog.section_ids_of_department(f.department_id))
            )
        if f.section_id is not None:
            query = query.where(Task.section_id == f.section_id)
        if f.project_id is not None or f.node_id is not None:
            placed = select(Placement.task_id)
            if f.project_id is not None:
                placed = placed.where(Placement.project_id == f.project_id)
            if f.node_id is not None:
                tree = next((t for t in catalog.projects.values() if f.node_id in t.nodes), None)
                subtree = tree.outline.subtree(f.node_id) if tree else set[int]()
                placed = placed.where(Placement.node_id.in_(subtree))
            query = query.where(Task.id.in_(placed))
        if f.person_id is not None:
            leads = Task.lead_person_id == f.person_id
            helps = Task.id.in_(
                select(TaskHelper.task_id).where(TaskHelper.person_id == f.person_id)
            )
            query = query.where(
                {
                    PersonRole.LEAD: leads,
                    PersonRole.HELPER: helps,
                    PersonRole.ANY: or_(leads, helps),
                }[f.person_role]
            )
        return query

    def find(self, key: str) -> Task:
        """A task the principal can see; invisible tasks are reported as not found."""
        try:
            normalized = normalize_key(key)
        except InvalidTaskKeyError as error:
            raise NotFoundError(f"no task {key}") from error
        query = visible_tasks(select(Task).where(Task.key == normalized), self.principal)
        task = self.session.scalars(with_card_data(query)).one_or_none()
        if task is None:
            raise NotFoundError(f"no task {key}")
        return task

    def _find_for(self, key: str, permission: Permission) -> Task:
        task = self.find(key)
        self.principal.require(permission, task.section_id)
        return task

    def _detail(self, task: Task, catalog: Catalog) -> TaskDetail:
        total = self.session.scalar(select(func.count()).select_from(Task)) or 0
        return TaskDetail(
            **summarize(task, catalog).model_dump(),
            created_at=task.created_at,
            updated_at=task.updated_at,
            rank_total=total,
            post_count=self.session.scalar(select(func.count()).where(Post.task_id == task.id))
            or 0,
            permissions=TaskPermissions(
                edit=self.principal.can(Permission.TASK_EDIT, task.section_id),
                comment=self.principal.can(Permission.TASK_COMMENT, task.section_id),
                delete=self.principal.can(Permission.TASK_DELETE, task.section_id),
            ),
        )

    # ------------------------------------------------------------------ commands

    def create(self, data: TaskCreate) -> TaskDetail:
        catalog = Catalog.load(self.session)
        catalog.require_section(data.section_id)
        self.principal.require(Permission.TASK_EDIT, data.section_id)
        catalog.require_person(data.lead_id)
        helpers = self._validated_helpers(data.helper_ids, data.lead_id, catalog)
        projects = [p.project_id for p in data.placements]
        if len(projects) != len(set(projects)):
            raise RuleViolationError("a task can sit in only one place per project")
        for placement in data.placements:
            catalog.tree(placement.project_id).require_node(placement.node_id)

        acquire_lock(self.session, TASK_RANKING_LOCK)
        count = self.session.scalar(select(func.count()).select_from(Task)) or 0
        task = Task(
            key=generate_unique_key(self._key_exists),
            title=data.title,
            description=data.description,
            status=data.status,
            rank=count + 1,  # new tasks start at the bottom of the team ranking
            lead_person_id=data.lead_id,
            section_id=data.section_id,
            created_by_user_id=self.principal.user_id,
            helpers=[TaskHelper(person_id=pid) for pid in helpers],
            placements=[
                Placement(project_id=p.project_id, node_id=p.node_id) for p in data.placements
            ],
        )
        self.session.add(task)
        self.session.flush()
        self._event(task, EventKind.CREATED, {})
        self.session.commit()
        return self._detail(task, catalog)

    def update(self, key: str, data: TaskUpdate) -> TaskDetail:
        catalog = Catalog.load(self.session)
        task = self._find_for(key, Permission.TASK_EDIT)
        if data.version != task.version:
            raise StaleVersionError("someone else changed this task; reload it and try again")

        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.section_id is not None and data.section_id != task.section_id:
            catalog.require_section(data.section_id)
            self.principal.require(Permission.TASK_EDIT, data.section_id)  # rule: both sections
            self._event(
                task, EventKind.SECTION_CHANGED, {"from": task.section_id, "to": data.section_id}
            )
            task.section_id = data.section_id
        if data.status is not None and data.status != task.status:
            self._event(
                task, EventKind.STATUS_CHANGED, {"from": task.status.value, "to": data.status.value}
            )
            task.status = data.status
        if data.lead_id is not None and data.lead_id != task.lead_person_id:
            catalog.require_person(data.lead_id)
            self._event(
                task, EventKind.LEAD_CHANGED, {"from": task.lead_person_id, "to": data.lead_id}
            )
            task.lead_person_id = data.lead_id
        wanted = (
            self._validated_helpers(data.helper_ids, task.lead_person_id, catalog)
            if data.helper_ids is not None
            else [h.person_id for h in task.helpers if h.person_id != task.lead_person_id]
        )
        self._set_helpers(task, wanted, record_events=data.helper_ids is not None)

        task.updated_at = utcnow()  # always an UPDATE of the row, so `version` goes up
        self.session.commit()
        return self._detail(task, catalog)

    def move(self, key: str, data: TaskMove) -> TaskDetail:
        task = self._find_for(key, Permission.TASK_EDIT)
        target = self.find(data.target)
        acquire_lock(self.session, TASK_RANKING_LOCK)
        # Read the ranks again under the lock: another move may have committed in the meantime.
        current, target_rank = (
            self.session.scalar(select(Task.rank).where(Task.id == task_id)) or 0
            for task_id in (task.id, target.id)
        )
        count = self.session.scalar(select(func.count()).select_from(Task)) or 0
        shift = plan_move(current, target_rank, data.where, count)
        if not shift.is_noop:
            self._shift_ranks(shift.lo, shift.hi, shift.delta, exclude_id=task.id)
            self.session.execute(
                update(Task)
                .where(Task.id == task.id)
                .values(rank=shift.new_rank, updated_at=Task.updated_at),
                execution_options={"synchronize_session": False},
            )
        self.session.commit()
        self.session.expire_all()
        return self._detail(self.find(task.key), Catalog.load(self.session))

    def delete(self, key: str) -> None:
        task = self._find_for(key, Permission.TASK_DELETE)
        acquire_lock(self.session, TASK_RANKING_LOCK)
        rank = self.session.scalar(select(Task.rank).where(Task.id == task.id)) or 0
        files = list(
            self.session.scalars(select(Attachment.public_id).where(Attachment.task_id == task.id))
        )
        for model in (Attachment, Post, Event):
            self.session.execute(delete(model).where(model.task_id == task.id))
        self.session.delete(task)  # helpers and placements go with it (ORM cascade)
        self.session.flush()
        count = self.session.scalar(select(func.count()).select_from(Task)) or 0
        self._shift_ranks(rank + 1, count + 1, -1)
        self.session.commit()
        if self.store is not None:
            for public_id in files:
                self.store.delete(public_id)

    # ------------------------------------------------------------------ placements

    def add_placement(self, key: str, data: PlacementIn) -> TaskDetail:
        catalog = Catalog.load(self.session)
        task = self._find_for(key, Permission.TASK_EDIT)
        tree = catalog.tree(data.project_id)
        tree.require_node(data.node_id)
        if any(p.project_id == data.project_id for p in task.placements):
            raise ConflictError(f"already in {tree.project.name}: move it there instead")
        task.placements.append(Placement(project_id=data.project_id, node_id=data.node_id))
        self._event(
            task, EventKind.PLACEMENT_ADDED, {"project": data.project_id, "node": data.node_id}
        )
        return self._save(task, catalog)

    def move_placement(self, key: str, project_id: int, data: PlacementMove) -> TaskDetail:
        catalog = Catalog.load(self.session)
        task = self._find_for(key, Permission.TASK_EDIT)
        placement = self._placement(task, project_id)
        catalog.tree(project_id).require_node(data.node_id)
        if placement.node_id != data.node_id:
            self._event(
                task,
                EventKind.PLACEMENT_MOVED,
                {"project": project_id, "from": placement.node_id, "to": data.node_id},
            )
            placement.node_id = data.node_id
        return self._save(task, catalog)

    def remove_placement(self, key: str, project_id: int) -> TaskDetail:
        catalog = Catalog.load(self.session)
        task = self._find_for(key, Permission.TASK_EDIT)
        placement = self._placement(task, project_id)
        task.placements.remove(placement)
        self._event(
            task, EventKind.PLACEMENT_REMOVED, {"project": project_id, "node": placement.node_id}
        )
        return self._save(task, catalog)

    # ------------------------------------------------------------------ helpers

    def _key_exists(self, key: str) -> bool:
        return self.session.scalar(select(Task.id).where(Task.key == key)) is not None

    def _save(self, task: Task, catalog: Catalog) -> TaskDetail:
        task.updated_at = utcnow()
        self.session.commit()
        return self._detail(task, catalog)

    @staticmethod
    def _placement(task: Task, project_id: int) -> Placement:
        for placement in task.placements:
            if placement.project_id == project_id:
                return placement
        raise NotFoundError(f"the task is not in project {project_id}")

    @staticmethod
    def _validated_helpers(ids: list[int], lead_id: int, catalog: Catalog) -> list[int]:
        """Unique, existing people; the lead is never also a helper."""
        result: list[int] = []
        for person_id in ids:
            catalog.require_person(person_id)
            if person_id != lead_id and person_id not in result:
                result.append(person_id)
        return result

    def _set_helpers(self, task: Task, wanted: list[int], *, record_events: bool) -> None:
        current = {h.person_id: h for h in task.helpers}
        for person_id, helper in current.items():
            if person_id not in wanted:
                task.helpers.remove(helper)
                if record_events:
                    self._event(task, EventKind.HELPER_REMOVED, {"person": person_id})
        for person_id in wanted:
            if person_id not in current:
                task.helpers.append(TaskHelper(person_id=person_id))
                if record_events:
                    self._event(task, EventKind.HELPER_ADDED, {"person": person_id})

    def _shift_ranks(self, lo: int, hi: int, delta: int, exclude_id: int | None = None) -> None:
        query = update(Task).where(Task.rank >= lo, Task.rank <= hi)
        if exclude_id is not None:
            query = query.where(Task.id != exclude_id)
        # `updated_at=Task.updated_at` keeps the column's on-update default from firing:
        # re-ranking is not an edit of the task.
        self.session.execute(
            query.values(rank=Task.rank + delta, updated_at=Task.updated_at),
            execution_options={"synchronize_session": False},
        )

    def _event(self, task: Task, kind: EventKind, data: dict[str, Any]) -> None:
        self.session.add(
            Event(task_id=task.id, actor_user_id=self.principal.user_id, kind=kind, data=data)
        )
