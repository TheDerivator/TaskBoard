"""Project endpoints: projects with node trees and counts, outlines, project and node editing."""

from fastapi import APIRouter, status

from taskboard.api.deps import Projects
from taskboard.schemas.projects import (
    NodeCreate,
    NodeUpdate,
    ProjectCreate,
    ProjectOut,
    ProjectOutline,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(projects: Projects, include_archived: bool = False) -> list[ProjectOut]:
    return projects.list(include_archived=include_archived)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, projects: Projects) -> ProjectOut:
    return projects.create(body)


@router.get("/{key}/outline")
def project_outline(
    key: str, projects: Projects, node: int | None = None, include_archived: bool = False
) -> ProjectOutline:
    """The project, or one node's subtree, as a numbered outline with its tasks in rank order."""
    return projects.outline(key, node_id=node, include_archived=include_archived)


@router.patch("/{key}")
def update_project(key: str, body: ProjectUpdate, projects: Projects) -> ProjectOut:
    return projects.update(key, body)


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(key: str, projects: Projects) -> None:
    """Deletes the project and its placements; the tasks themselves stay."""
    projects.delete(key)


@router.post("/{key}/nodes", status_code=status.HTTP_201_CREATED)
def add_node(key: str, body: NodeCreate, projects: Projects) -> ProjectOut:
    return projects.add_node(key, body)


@router.patch("/{key}/nodes/{node_id}")
def update_node(key: str, node_id: int, body: NodeUpdate, projects: Projects) -> ProjectOut:
    """Rename, and/or move under `parent_id` (null = top level) at `index`."""
    return projects.update_node(key, node_id, body)


@router.delete("/{key}/nodes/{node_id}")
def delete_node(key: str, node_id: int, projects: Projects) -> ProjectOut:
    """Deletes the node and its subtree; tasks placed there move to the node's parent."""
    return projects.delete_node(key, node_id)
