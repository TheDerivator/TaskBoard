"""Shapes for login, password change and the current-user ("me") document."""

from pydantic import BaseModel, Field

from taskboard.domain.access import Permission
from taskboard.identity.principal import Principal
from taskboard.identity.providers import IdentityProviders
from taskboard.schemas.tokens import TokenInfo


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1000)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(max_length=1000)
    new_password: str = Field(max_length=1000)


class PermissionReach(BaseModel):
    """Where a permission applies. The frontend uses this to show or hide controls only; the
    server enforces every rule itself."""

    everywhere: bool
    section_ids: list[int]


class LoginProvider(BaseModel):
    name: str
    display_name: str


class WindowsLogin(BaseModel):
    automatic: bool  # the page tries it by itself when it loads, without being asked


class LoginOptions(BaseModel):
    password: bool
    providers: list[LoginProvider]
    # Windows sign-in by the app itself (POST /api/auth/windows), when it is switched on.
    windows: WindowsLogin | None = None


class Me(BaseModel):
    username: str
    display_name: str
    is_anonymous: bool
    person_id: int | None
    must_change_password: bool
    # The display name of the proxy sign-in that identifies this user on every request, if any
    # (e.g. "Windows sign-in"); such users cannot log out.
    signed_in_by: str | None = None
    # The API token this request came with (D-097); None in a browser.
    api_token: TokenInfo | None = None
    permissions: dict[Permission, PermissionReach]
    login: LoginOptions

    @classmethod
    def build(cls, principal: Principal, providers: IdentityProviders) -> Me:
        permissions: dict[Permission, PermissionReach] = {}
        for permission in Permission:
            reach = principal.reach(permission)
            permissions[permission] = PermissionReach(
                everywhere=reach.everywhere, section_ids=sorted(reach.section_ids)
            )
        return cls(
            username=principal.username,
            display_name=principal.display_name,
            is_anonymous=principal.is_anonymous,
            person_id=principal.person_id,
            must_change_password=principal.must_change_password,
            signed_in_by=next(
                (p.display_name for p in providers.ambient if p.name == principal.ambient_provider),
                None,
            ),
            api_token=TokenInfo(name=principal.token_name, scope=principal.token_scope)
            if principal.token_name is not None and principal.token_scope is not None
            else None,
            permissions=permissions,
            login=LoginOptions(
                password=True,
                providers=[
                    LoginProvider(name=p.name, display_name=p.display_name)
                    for p in providers.redirect.values()
                ],
                windows=WindowsLogin(automatic=providers.negotiate.automatic)
                if providers.negotiate
                else None,
            ),
        )
