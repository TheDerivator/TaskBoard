"""Authentication endpoints: current user, password login, logout, change own password."""

from fastapi import APIRouter, Request, Response, status

from taskboard.api.client import client_ip
from taskboard.api.cookies import set_session_cookie
from taskboard.api.deps import AppSettings, Auth, CurrentPrincipal, Providers
from taskboard.identity.sessions import SESSION_COOKIE
from taskboard.schemas.auth import LoginRequest, Me, PasswordChangeRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/me")
def me(principal: CurrentPrincipal, providers: Providers) -> Me:
    """Who is calling (possibly the anonymous visitor) and what they may do."""
    return Me.build(principal, providers)


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: Auth,
    settings: AppSettings,
    providers: Providers,
) -> Me:
    principal, token = auth.login(
        body.username,
        body.password,
        ip_address=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, request, settings, token)
    return Me.build(principal, providers)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, auth: Auth) -> None:
    auth.logout(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChangeRequest, request: Request, principal: CurrentPrincipal, auth: Auth
) -> None:
    """Change your own password. Your other sessions are logged out."""
    auth.change_password(
        principal,
        current_password=body.current_password,
        new_password=body.new_password,
        session_token=request.cookies.get(SESSION_COOKIE),
    )
