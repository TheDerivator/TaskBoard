"""Recent activity shapes (M25): what to list; tasks and process changes by their newest post."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from taskboard.domain.activity import (
    CURSOR_PATTERN,
    DEFAULT_PAGE,
    MAX_PAGE,
    ActivityType,
    PostKind,
)
from taskboard.schemas.changes import ChangeSummary
from taskboard.schemas.conversation import Actor
from taskboard.schemas.tasks import TaskSummary


class ActivityQuery(BaseModel):
    """What to list, and which page. A filter that does not apply to a type leaves that type out:
    process changes sit in no project, tasks in no process."""

    types: list[ActivityType] | None = None  # None: every type you may see
    department_id: int | None = None
    section_id: int | None = None  # a task's section, a process's owning section
    project_id: int | None = None  # tasks only
    node_id: int | None = None  # tasks only: the node and everything below it
    process_id: int | None = None  # process changes only
    limit: int = Field(DEFAULT_PAGE, ge=1, le=MAX_PAGE)
    before: str | None = Field(None, pattern=CURSOR_PATTERN)  # the `next` of the page before


class LastPost(BaseModel):
    """The newest post of a task's or a process change's conversation."""

    id: int
    kind: PostKind
    author: Actor
    created_at: datetime
    excerpt: str  # one line of plain text, about 200 characters


class TaskActivity(BaseModel):
    type: Literal["task"] = "task"
    task: TaskSummary
    last_post: LastPost
    post_count: int


class ChangeActivity(BaseModel):
    type: Literal["change"] = "change"
    change: ChangeSummary
    last_post: LastPost
    post_count: int


ActivityItem = Annotated[TaskActivity | ChangeActivity, Field(discriminator="type")]


class ActivityPage(BaseModel):
    items: list[ActivityItem]  # newest post first
    next: str | None  # pass as `before` for what is older; None: nothing older
