"""Reference endpoints: the bootstrap document and the people list."""

from fastapi import APIRouter

from taskboard.api.deps import Providers, Reference
from taskboard.schemas.reference import Bootstrap, PersonOut

router = APIRouter(tags=["reference"])


@router.get("/bootstrap")
def bootstrap(reference: Reference, providers: Providers) -> Bootstrap:
    """Everything the app needs to start: who am I, departments, people, projects, statuses."""
    return reference.bootstrap(providers)


@router.get("/people")
def people(reference: Reference) -> list[PersonOut]:
    return reference.people()
