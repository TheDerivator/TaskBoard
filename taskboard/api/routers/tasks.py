"""Task endpoints: list/filter, read, create, edit, move in the ranking, delete, placements."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from taskboard.api.deps import Tasks
from taskboard.schemas.tasks import (
    PlacementIn,
    PlacementMove,
    TaskCreate,
    TaskDetail,
    TaskFilter,
    TaskList,
    TaskMove,
    TaskUpdate,
)

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(tasks: Tasks, filters: Annotated[TaskFilter, Query()]) -> TaskList:
    """Visible tasks in team-wide rank order. Filters hide tasks; ranks stay global."""
    return tasks.list(filters)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreate, tasks: Tasks) -> TaskDetail:
    """New tasks start at the bottom of the ranking."""
    return tasks.create(body)


@router.get("/{key}")
def get_task(key: str, tasks: Tasks) -> TaskDetail:
    """`key` accepts `K7Q2MX`, `T-K7Q2MX`, any case."""
    return tasks.get(key)


@router.patch("/{key}")
def update_task(key: str, body: TaskUpdate, tasks: Tasks) -> TaskDetail:
    """Change the fields sent; `version` must match or the answer is 409 `stale`."""
    return tasks.update(key, body)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(key: str, tasks: Tasks) -> None:
    tasks.delete(key)


@router.post("/{key}/move")
def move_task(key: str, body: TaskMove, tasks: Tasks) -> TaskDetail:
    """Put the task directly before or after `target` in the team-wide ranking."""
    return tasks.move(key, body)


@router.post("/{key}/placements", status_code=status.HTTP_201_CREATED)
def add_placement(key: str, body: PlacementIn, tasks: Tasks) -> TaskDetail:
    """Add the task to another project (one place per project)."""
    return tasks.add_placement(key, body)


@router.put("/{key}/placements/{project_id}")
def move_placement(key: str, project_id: int, body: PlacementMove, tasks: Tasks) -> TaskDetail:
    return tasks.move_placement(key, project_id, body)


@router.delete("/{key}/placements/{project_id}")
def remove_placement(key: str, project_id: int, tasks: Tasks) -> TaskDetail:
    return tasks.remove_placement(key, project_id)
