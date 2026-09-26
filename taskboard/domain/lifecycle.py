"""Task lifecycle: idea → started → done → archived, and which states are shown by default."""

from enum import StrEnum


class TaskStatus(StrEnum):
    """Lifecycle state of a task. The picker allows any transition; the order is for display."""

    IDEA = "idea"
    STARTED = "started"
    DONE = "done"
    ARCHIVED = "archived"

    @property
    def label(self) -> str:
        return self.value.capitalize()


# DESIGN rule 4: Idea, Started and Done are shown; Archived is hidden unless asked for.
DEFAULT_VISIBLE_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.IDEA, TaskStatus.STARTED, TaskStatus.DONE}
)
