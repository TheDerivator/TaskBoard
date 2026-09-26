"""Kinds of automatic task events shown in the conversation timeline."""

from enum import StrEnum


class EventKind(StrEnum):
    CREATED = "created"
    STATUS_CHANGED = "status_changed"  # data: {"from": "idea", "to": "started"}
    LEAD_CHANGED = "lead_changed"  # data: {"from": person_id, "to": person_id}
    HELPER_ADDED = "helper_added"  # data: {"person": person_id}
    HELPER_REMOVED = "helper_removed"  # data: {"person": person_id}
    SECTION_CHANGED = "section_changed"  # data: {"from": section_id, "to": section_id}
    PLACEMENT_ADDED = "placement_added"  # data: {"project": id, "node": id | None}
    PLACEMENT_MOVED = "placement_moved"  # data: {"project": id, "from": id | None, "to": id | None}
    PLACEMENT_REMOVED = "placement_removed"  # data: {"project": id, "node": id | None}
