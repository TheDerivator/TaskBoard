"""HTTP API layer: thin FastAPI routers, request dependencies, error mapping. Mounted at `/api`."""

from fastapi import APIRouter

from taskboard.api.routers import (
    admin,
    auth,
    conversation,
    meta,
    projects,
    reference,
    sso,
    tasks,
    windows,
)
from taskboard.identity.providers import IdentityProviders


def build_api_router(providers: IdentityProviders | None = None) -> APIRouter:
    """Collect every API router; the web layer mounts the result under `/api`.

    SSO sign-in routes exist only when a redirect provider (OpenID Connect) is configured, and
    the Windows sign-in route only when that is switched on.
    """
    router = APIRouter()
    router.include_router(meta.router)
    router.include_router(auth.router)
    if providers is not None and providers.redirect:
        router.include_router(sso.router)
    if providers is not None and providers.negotiate:
        router.include_router(windows.router)
    router.include_router(reference.router)
    router.include_router(tasks.router)
    router.include_router(projects.router)
    router.include_router(conversation.router)
    router.include_router(admin.router)
    return router
