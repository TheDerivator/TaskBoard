"""Search everything (M19): tasks, process changes, knowledge boxes and defects you may see."""

from typing import Annotated

from fastapi import APIRouter, Query

from taskboard.api.deps import Search
from taskboard.schemas.search import SearchResults

router = APIRouter(tags=["search"])


@router.get("/search")
def search(
    q: Annotated[str, Query(max_length=200)],
    search: Search,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResults:
    """Every word of `q` must match (ignoring case); grouped by type, best matches first, each
    type with its total. Only what you may see is searched."""
    return search.search(q, limit)
