"""Recent activity (M25): tasks and process changes you may see, by their newest post."""

from typing import Annotated

from fastapi import APIRouter, Query

from taskboard.api.deps import Activity
from taskboard.schemas.activity import ActivityPage, ActivityQuery

router = APIRouter(tags=["activity"])


@router.get("/activity")
def recent_activity(activity: Activity, query: Annotated[ActivityQuery, Query()]) -> ActivityPage:
    """Newest post first: comments, status updates and periods (automatic events and edits do
    not count). `project_id`/`node_id` list tasks only, `process_id` process changes only. For
    older items, pass the page's `next` as `before`."""
    return activity.recent(query)
