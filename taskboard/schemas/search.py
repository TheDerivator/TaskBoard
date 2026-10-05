"""Search results (M19): grouped by type (knowledge, process changes, tasks, defects), each hit
with its stable link and a line of context."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

SearchType = Literal["knowledge", "changes", "tasks", "defects"]


class SearchHit(BaseModel):
    type: SearchType
    key: str  # the box key, change key or task key
    ref: str  # what people call it: "CC-31", "T-104"; "" for boxes
    title: str
    context: str  # kind and place, or a snippet around the match
    url: str  # the stable link, app-relative: "/knowledge/STL/CC/m-powder"
    style: str | None = None  # a box's kind palette entry (the swatch)
    process: str | None = None  # a change's process
    state: str | None = None  # a change's state ("in_effect", ...): the client words it
    state_date: date | None = None


class SearchGroup(BaseModel):
    type: SearchType
    total: int  # all matches; `hits` holds the best ones
    hits: list[SearchHit]


class SearchResults(BaseModel):
    query: str
    groups: list[SearchGroup]  # in the dialog's order; only the types you may see
