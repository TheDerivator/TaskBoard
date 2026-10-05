"""Process-knowledge endpoints: a process's map, boxes (with links, controls, external links),
history, references from changes and tasks, and the kinds & link types settings."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile, status

from taskboard.api.deps import Knowledge, Releases
from taskboard.schemas.conversation import AttachmentOut
from taskboard.schemas.knowledge import (
    BoxCreate,
    BoxMove,
    BoxOut,
    BoxRef,
    BoxRelated,
    BoxSaved,
    BoxUpdate,
    ControlPlan,
    KindIn,
    KindUpdate,
    LinkTypeIn,
    LinkTypeUpdate,
    MapGraph,
    MapSettings,
    ReleaseIn,
    ReleaseList,
    ReleaseOut,
    RevisionOut,
)
from taskboard.services.attachments import MAX_ATTACHMENT_BYTES

router = APIRouter(tags=["process knowledge"])


@router.get("/processes/{code}/map")
def process_map(code: str, knowledge: Knowledge, release: int | None = None) -> MapGraph:
    """The map (boxes, links, controls), its department's defects and linked boxes elsewhere;
    with `release` (3 for v3), what that FMEA and control plan version froze."""
    return knowledge.graph(code, release)


@router.get("/processes/{code}/releases")
def process_releases(code: str, releases: Releases) -> ReleaseList:
    """Released versions of the FMEA and control plan, and the draft since the latest one."""
    return releases.releases(code)


@router.post("/processes/{code}/releases", status_code=status.HTTP_201_CREATED)
def release(code: str, body: ReleaseIn, releases: Releases) -> ReleaseOut:
    """Release the draft as the next version (no approval step); 409 if `base` is not the latest."""
    return releases.release(code, body)


@router.post("/processes/{code}/map", status_code=status.HTTP_201_CREATED)
def start_map(code: str, knowledge: Knowledge) -> BoxOut:
    """ "Start the map": its root is the process itself."""
    return knowledge.start_map(code)


@router.get("/control-plan")
def control_plan(
    department: str, knowledge: Knowledge, process: str | None = None, release: int | None = None
) -> ControlPlan:
    """A department's defects, what leads to each (in any map you can see) and its controls; with
    `process` and `release`, what that version of the process's control plan froze."""
    return knowledge.control_plan(department, process, release)


@router.get("/boxes")
def find_boxes(q: str, knowledge: Knowledge) -> list[BoxRef]:
    """Boxes whose name or key contains `q`, in every map and defect catalogue you can see."""
    return knowledge.find_boxes(q)


@router.post("/boxes/{key}/attachments", status_code=status.HTTP_201_CREATED)
def upload_box_image(
    key: str, file: Annotated[UploadFile, File()], knowledge: Knowledge
) -> AttachmentOut:
    """An image (PNG, JPEG, GIF, WebP; at most 10 MB) for the box's description."""
    data = file.file.read(MAX_ATTACHMENT_BYTES + 1)
    return knowledge.upload(key, file.filename, data)


@router.post("/boxes", status_code=status.HTTP_201_CREATED)
def create_box(body: BoxCreate, knowledge: Knowledge) -> BoxSaved:
    """Under `parent_key`, or (a defect) in a section's catalogue. Links and controls included."""
    return knowledge.create_box(body)


@router.get("/boxes/{key}")
def get_box(key: str, knowledge: Knowledge) -> BoxSaved:
    return knowledge.saved(key)


@router.patch("/boxes/{key}")
def update_box(key: str, body: BoxUpdate, knowledge: Knowledge) -> BoxSaved:
    """Saves the box, its outgoing links and its controls together; each changed one gets a new
    revision. `version` must be the one last read (else 409)."""
    return knowledge.update_box(key, body)


@router.post("/boxes/{key}/move")
def move_box(key: str, body: BoxMove, knowledge: Knowledge) -> BoxSaved:
    """Another place in the same map: under `parent_key`, before `before_key` (or last)."""
    return knowledge.move_box(key, body)


@router.delete("/boxes/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_box(key: str, knowledge: Knowledge) -> None:
    """Only without boxes under it; its links, controls and references go with it."""
    knowledge.delete_box(key)


@router.post("/boxes/{key}/reviewed")
def mark_reviewed(key: str, knowledge: Knowledge) -> BoxSaved:
    """Checked today and still right."""
    return knowledge.mark_reviewed(key)


@router.get("/boxes/{key}/history")
def box_history(key: str, knowledge: Knowledge) -> list[RevisionOut]:
    """Revisions of the box, its controls and its outgoing links, newest first."""
    return knowledge.history(key)


@router.get("/boxes/{key}/related")
def box_related(key: str, knowledge: Knowledge) -> BoxRelated:
    """Process changes on this box or below it, and tasks about it."""
    return knowledge.related(key)


@router.get("/changes/{key}/boxes")
def change_boxes(key: str, knowledge: Knowledge) -> list[BoxRef]:
    """Where in the knowledge map the change sits."""
    return knowledge.change_boxes(key)


@router.put("/changes/{key}/boxes/{box_key}")
def link_change(key: str, box_key: str, knowledge: Knowledge) -> list[BoxRef]:
    return knowledge.link_change(key, box_key)


@router.delete("/changes/{key}/boxes/{box_key}")
def unlink_change(key: str, box_key: str, knowledge: Knowledge) -> list[BoxRef]:
    return knowledge.link_change(key, box_key, linked=False)


@router.get("/tasks/{key}/boxes")
def task_boxes(key: str, knowledge: Knowledge) -> list[BoxRef]:
    return knowledge.task_boxes(key)


@router.put("/tasks/{key}/boxes/{box_key}")
def link_task(key: str, box_key: str, knowledge: Knowledge) -> list[BoxRef]:
    return knowledge.link_task(key, box_key)


@router.delete("/tasks/{key}/boxes/{box_key}")
def unlink_task(key: str, box_key: str, knowledge: Knowledge) -> list[BoxRef]:
    return knowledge.link_task(key, box_key, linked=False)


@router.get("/map-settings")
def map_settings(knowledge: Knowledge) -> MapSettings:
    """Box kinds and link types, shared by every process map."""
    return knowledge.settings()


@router.post("/box-kinds", status_code=status.HTTP_201_CREATED)
def create_kind(body: KindIn, knowledge: Knowledge) -> MapSettings:
    return knowledge.create_kind(body)


@router.patch("/box-kinds/{key}")
def update_kind(key: str, body: KindUpdate, knowledge: Knowledge) -> MapSettings:
    return knowledge.update_kind(key, body)


@router.delete("/box-kinds/{key}")
def delete_kind(key: str, knowledge: Knowledge) -> MapSettings:
    """Custom kinds only, and only while no box has it."""
    return knowledge.delete_kind(key)


@router.post("/link-types", status_code=status.HTTP_201_CREATED)
def create_link_type(body: LinkTypeIn, knowledge: Knowledge) -> MapSettings:
    return knowledge.create_link_type(body)


@router.patch("/link-types/{key}")
def update_link_type(key: str, body: LinkTypeUpdate, knowledge: Knowledge) -> MapSettings:
    return knowledge.update_link_type(key, body)


@router.delete("/link-types/{key}")
def delete_link_type(key: str, knowledge: Knowledge) -> MapSettings:
    """Custom link types only, and only while no link has it."""
    return knowledge.delete_link_type(key)
