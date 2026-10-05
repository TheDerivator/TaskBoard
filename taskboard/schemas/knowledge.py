"""Process-knowledge shapes: kinds and link types, a map (boxes, links, controls, external links),
box edit commands, references from tasks and changes, revisions (history) and releases."""

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.knowledge import (
    BoxRole,
    ControlKind,
    ExternalLinkKind,
    LinkRole,
    ObjectType,
)
from taskboard.domain.releases import Document, Verb
from taskboard.schemas.conversation import Actor

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Markdown = Annotated[str, StringConstraints(max_length=20_000)]
Key = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_-]{0,39}$")]
UrlText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=2000)]


# ---------------------------------------------------------------- settings


class FieldDef(BaseModel):
    """An extra field of a kind or link type (DESIGN principle 1)."""

    key: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_]{0,39}$")]
    label: Annotated[str, StringConstraints(max_length=100)] = ""
    type: Literal["text", "number"] = "text"


class KindOut(BaseModel):
    key: str
    name: str
    description: str
    role: BoxRole
    style: str
    has_facts: bool
    has_main_url: bool
    builtin: bool
    position: int
    field_schema: list[FieldDef]
    box_count: int = 0


class KindIn(BaseModel):
    """A custom kind (its role is plain; the built-in kinds carry the behaviour)."""

    key: Key | None = None  # default: from the name
    name: ShortName
    description: Annotated[str, StringConstraints(max_length=2000)] = ""
    style: str = "grey"
    has_facts: bool = False
    has_main_url: bool = False
    field_schema: list[FieldDef] = Field(default_factory=list[FieldDef])


class KindUpdate(BaseModel):
    name: ShortName | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    style: str | None = None
    has_facts: bool | None = None
    has_main_url: bool | None = None
    field_schema: list[FieldDef] | None = None
    position: int | None = None


class LinkTypeOut(BaseModel):
    key: str
    forward_name: str
    backward_name: str
    description: str
    role: LinkRole
    builtin: bool
    position: int
    field_schema: list[FieldDef]
    link_count: int = 0


class LinkTypeIn(BaseModel):
    key: Key | None = None
    forward_name: ShortName
    backward_name: ShortName
    description: Annotated[str, StringConstraints(max_length=2000)] = ""
    field_schema: list[FieldDef] = Field(default_factory=list[FieldDef])


class LinkTypeUpdate(BaseModel):
    forward_name: ShortName | None = None
    backward_name: ShortName | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    field_schema: list[FieldDef] | None = None
    position: int | None = None


class MapSettings(BaseModel):
    kinds: list[KindOut]
    link_types: list[LinkTypeOut]
    can_configure: bool


# ---------------------------------------------------------------- the map


class ExternalLinkIn(BaseModel):
    kind: ExternalLinkKind
    label: Name
    url: UrlText
    pass_box_param: bool = False


class ExternalLinkOut(ExternalLinkIn):
    href: str  # the address to open: `url`, with `?node=<box key>` when asked


class BoxOut(BaseModel):
    key: str
    process_id: int | None  # None for a defect (the department's catalogue)
    section_id: int  # the owning section: the process's, or the defect's own
    parent_key: str | None
    position: int
    kind: str  # the kind's key
    name: str
    body_md: str
    body_html: str
    main_url: str | None
    facts: list[list[str]]
    fields: dict[str, Any]
    step_no: str | None
    owner_person_id: int | None
    reviewed_at: date | None
    external_links: list[ExternalLinkOut]
    rev: int
    version: int  # send it back when editing (else HTTP 409)


class LinkOut(BaseModel):
    id: int
    type: str  # the link type's key
    from_key: str
    to_key: str
    note_md: str
    note_html: str
    fields: dict[str, Any]
    rev: int


class ControlOut(BaseModel):
    id: int
    box_key: str
    kind: ControlKind
    text: str
    position: int
    fields: dict[str, Any]
    external_links: list[ExternalLinkOut]
    rev: int


class MapProcess(BaseModel):
    id: int
    code: str
    name: str
    section_id: int
    department_id: int


class MapGraph(BaseModel):
    """A process's map: its boxes, the defects of its department, and boxes elsewhere that are
    linked to it; the links and controls between them; the kinds and link types to draw them."""

    process: MapProcess
    root_key: str | None  # None: no map yet ("Start the map")
    boxes: list[BoxOut]
    links: list[LinkOut]
    controls: list[ControlOut]
    kinds: list[KindOut]
    link_types: list[LinkTypeOut]
    change_counts: dict[str, int]  # process changes attached to each box (not rolled up)
    can_edit: bool


class PlanDepartment(BaseModel):
    id: int
    code: str
    name: str


class ControlPlan(BaseModel):
    """A department's defects and what leads to them (the CPL view): the defects, the boxes in
    any map that lead to one, the boxes above those causes, the leads-to links into the defects,
    and the causes' controls; the kinds and link types to draw them."""

    department: PlanDepartment
    boxes: list[BoxOut]
    links: list[LinkOut]
    controls: list[ControlOut]
    kinds: list[KindOut]
    link_types: list[LinkTypeOut]
    defect_sections: list[int]  # sections of the department where you may add defects


class LinkIn(BaseModel):
    """A link of the box being saved, with the box `to_key`: from this box ("leads to") or, with
    `direction: backward`, from that box to this one ("caused by"). `id` keeps an existing link
    (and its history)."""

    id: int | None = None
    type: str
    to_key: str  # the other box
    direction: Literal["forward", "backward"] = "forward"
    note_md: Markdown = ""
    fields: dict[str, Any] = Field(default_factory=dict[str, Any])


class ControlIn(BaseModel):
    id: int | None = None
    kind: ControlKind
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    fields: dict[str, Any] = Field(default_factory=dict[str, Any])
    external_links: list[ExternalLinkIn] = Field(default_factory=list[ExternalLinkIn])


class BoxContent(BaseModel):
    """What the box editor saves, all at once."""

    kind: str
    name: Name
    body_md: Markdown = ""
    main_url: UrlText | None = None
    facts: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])
    fields: dict[str, Any] = Field(default_factory=dict[str, Any])
    step_no: Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)] | None = None
    owner_person_id: int | None = None
    external_links: list[ExternalLinkIn] = Field(default_factory=list[ExternalLinkIn])
    links: list[LinkIn] = Field(default_factory=list[LinkIn])  # every link of the box
    controls: list[ControlIn] = Field(default_factory=list[ControlIn])


class BoxCreate(BoxContent):
    """A map box goes under `parent_key`; a defect (kind with the defect role) names a section."""

    parent_key: str | None = None
    section_id: int | None = None  # defects only
    before_key: str | None = None  # place it before this sibling; default: last


class BoxUpdate(BoxContent):
    version: int


class BoxMove(BaseModel):
    parent_key: str
    before_key: str | None = None  # default: last among the new siblings


class BoxSaved(BaseModel):
    box: BoxOut
    links: list[LinkOut]  # both directions
    controls: list[ControlOut]


# ---------------------------------------------------------------- references and history


class BoxRef(BaseModel):
    """A box as a link target elsewhere ("Ladle metallurgy › Trim & stirring")."""

    key: str
    name: str
    kind: str
    process_id: int | None
    path: list[str]  # names from the root down to the parent


class RelatedChange(BaseModel):
    key: str
    title: str
    url: str
    state: str
    state_date: date | None
    box_key: str  # where it is attached (this box or one below it)


class RelatedTask(BaseModel):
    key: str
    ref: str
    title: str
    url: str


class BoxRelated(BaseModel):
    changes: list[RelatedChange]  # attached to this box or below it (DESIGN Module 2, rule 8)
    tasks: list[RelatedTask]


class RevisionOut(BaseModel):
    object_type: ObjectType
    object_id: int
    rev: int
    created_at: datetime
    author: Actor | None
    deleted: bool
    changed: list[str]  # fields that differ from the revision before
    summary: str  # "Control: Level sensor calibrated every [INTERVAL]"


# ---------------------------------------------------------------- releases (FMEA and control plan)


class ReleaseIn(BaseModel):
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=4000)] = ""
    # The release the draft was reviewed against (None: there is none yet). If someone released
    # meanwhile, the server refuses (409) rather than release what nobody reviewed.
    base: int | None


class ReleaseOut(BaseModel):
    number: int
    label: str  # "v3"
    note: str
    released_by: Actor | None
    released_at: datetime
    items: int  # boxes, links and controls frozen


class DraftLine(BaseModel):
    """One changed box, link or control: what changed, who changed it last, revisions a → b."""

    object_type: ObjectType
    verb: Verb
    summary: str
    author: Actor | None
    at: datetime | None
    before: int | None
    after: int | None


class DraftEntry(BaseModel):
    """The changes of one box (its own, its controls', its links'), as the release dialog lists."""

    box_key: str
    box_name: str
    verb: Verb
    documents: list[Document]
    lines: list[DraftLine]
    warnings: list[str]


class Draft(BaseModel):
    """What a release now would change (DESIGN Versioning 3: computed, never stored)."""

    base: int | None  # the latest release's number
    entries: list[DraftEntry]
    fmea: int  # entries that change the FMEA
    cpl: int  # entries that change the control plan
    outside_scope: int  # knowledge edits since the base: versioned per box only
    markers: dict[str, str]  # box key → "Control changed since v3" (the blue dots)


class ReleaseList(BaseModel):
    releases: list[ReleaseOut]  # newest first
    draft: Draft
    can_release: bool
