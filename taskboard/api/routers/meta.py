"""Service metadata endpoints: health check and version."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from taskboard import __version__

router = APIRouter(tags=["meta"])


class Health(BaseModel):
    status: Literal["ok"]
    version: str


@router.get("/health")
def health() -> Health:
    """Liveness probe for load balancers and service monitors."""
    return Health(status="ok", version=__version__)
