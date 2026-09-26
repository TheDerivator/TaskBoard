"""FastAPI dependencies: one DB session per request, the current principal, and services.

Requests with unsafe methods (POST, PUT, PATCH, DELETE) get a write session. Services commit
explicitly; whatever they leave uncommitted is rolled back when the session closes.
"""

from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from taskboard.api.client import proxy_host
from taskboard.config import Settings
from taskboard.db.session import Database
from taskboard.identity.principal import Principal
from taskboard.identity.providers import IdentityProviders
from taskboard.identity.sessions import SESSION_COOKIE
from taskboard.services.attachments import AttachmentStore
from taskboard.services.auth import AuthService
from taskboard.services.conversation import ConversationService
from taskboard.services.organization import OrganizationService
from taskboard.services.projects import ProjectService
from taskboard.services.reference import ReferenceService
from taskboard.services.sso import SsoService
from taskboard.services.tasks import TaskService
from taskboard.services.users import UserAdminService

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_providers(request: Request) -> IdentityProviders:
    return request.app.state.identity_providers


def get_db_session(request: Request) -> Generator[Session]:
    database: Database = request.app.state.database
    with database.new_session(write=request.method not in SAFE_METHODS) as session:
        yield session


DbSession = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
Providers = Annotated[IdentityProviders, Depends(get_providers)]


def get_auth_service(
    session: DbSession, settings: AppSettings, providers: Providers
) -> AuthService:
    return AuthService(session, settings, providers)


Auth = Annotated[AuthService, Depends(get_auth_service)]


def get_principal(request: Request, auth: Auth) -> Principal:
    return auth.principal_for_request(
        session_token=request.cookies.get(SESSION_COOKIE),
        headers=request.headers,
        proxy=proxy_host(request),
    )


CurrentPrincipal = Annotated[Principal, Depends(get_principal)]


def get_attachment_store(settings: AppSettings) -> AttachmentStore:
    return AttachmentStore(settings.uploads_dir)


Store = Annotated[AttachmentStore, Depends(get_attachment_store)]


def get_task_service(session: DbSession, principal: CurrentPrincipal, store: Store) -> TaskService:
    return TaskService(session, principal, store)


def get_conversation_service(
    session: DbSession, principal: CurrentPrincipal, store: Store
) -> ConversationService:
    return ConversationService(session, principal, store)


def get_project_service(session: DbSession, principal: CurrentPrincipal) -> ProjectService:
    return ProjectService(session, principal)


def get_reference_service(session: DbSession, principal: CurrentPrincipal) -> ReferenceService:
    return ReferenceService(session, principal)


Tasks = Annotated[TaskService, Depends(get_task_service)]
Projects = Annotated[ProjectService, Depends(get_project_service)]
Reference = Annotated[ReferenceService, Depends(get_reference_service)]
Conversations = Annotated[ConversationService, Depends(get_conversation_service)]


def get_user_admin(session: DbSession, principal: CurrentPrincipal) -> UserAdminService:
    return UserAdminService(session, principal)  # refuses without users.manage


def get_organization(session: DbSession, principal: CurrentPrincipal) -> OrganizationService:
    return OrganizationService(session, principal)  # refuses without people.manage


def get_sso_service(session: DbSession, settings: AppSettings, providers: Providers) -> SsoService:
    return SsoService(session, settings, providers)


UserAdmin = Annotated[UserAdminService, Depends(get_user_admin)]
Sso = Annotated[SsoService, Depends(get_sso_service)]
Organization = Annotated[OrganizationService, Depends(get_organization)]
