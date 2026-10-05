"""Process-change shapes: changes with their periods and derived state, edit commands, periods."""

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.changes import MAX_LABEL_LENGTH, MAX_TAG_LENGTH, ChangeState, PeriodKind
from taskboard.schemas.conversation import Body, PeriodOut

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Markdown = Annotated[str, StringConstraints(max_length=20_000)]
Label = Annotated[str, StringConstraints(max_length=MAX_LABEL_LENGTH)]
Tag = Annotated[str, StringConstraints(max_length=MAX_TAG_LENGTH)]


class StateOut(BaseModel):
    """The derived state (never stored) on the server's today, and the date its wording uses."""

    state: ChangeState
    date: date | None


class ChangeSummary(BaseModel):
    key: str  # "LM-07"; fixed, also when the change moves to another process
    url: str  # the change's page, e.g. "/changes/STL/LM/LM-07"
    process_id: int
    title: str
    what_md: str
    why_md: str
    owner_person_id: int
    periods: list[PeriodOut]  # by start date
    state: StateOut
    post_count: int  # comments and periods
    updated_at: datetime
    version: int
    box_keys: list[str] = []  # where it sits in the knowledge map (boxes the reader may see)


class ChangePermissions(BaseModel):
    edit: bool  # details and periods
    comment: bool
    delete: bool


class ChangeDetail(ChangeSummary):
    created_at: datetime
    what_html: str  # rendered and sanitized Markdown
    why_html: str
    permissions: ChangePermissions


class ChangeCreate(BaseModel):
    process_id: int
    title: Title
    what_md: Markdown = ""
    why_md: Markdown = ""
    owner_person_id: int


class ChangeUpdate(BaseModel):
    """Only the fields sent are changed. `version` must be the one last read (else HTTP 409)."""

    version: int
    title: Title | None = None
    what_md: Markdown | None = None
    why_md: Markdown | None = None
    owner_person_id: int | None = None
    process_id: int | None = None  # move to another process (the key stays)


class PeriodIn(BaseModel):
    """A test needs an end date; a process change has none (it may be ended later)."""

    kind: PeriodKind
    label: Label | None = None  # default: "Test" / "Process change"
    start_date: date
    end_date: date | None = None
    scope_tags: list[Tag] = Field(default_factory=list[str])
    body_md: Body = ""


class PeriodUpdate(BaseModel):
    """Only the fields sent are changed; `end_date: null` removes the end (a change only).
    "Set end date" on a process change is `{"end_date": "2026-10-31"}`."""

    kind: PeriodKind | None = None
    label: Label | None = None
    start_date: date | None = None
    end_date: date | None = None
    scope_tags: list[Tag] | None = None
    body_md: Body | None = None
