"""SSO sign-in in a real browser (milestone M9): the full redirect round trip.

The browser really navigates to the provider and back: the fake provider's sign-in page runs on
its own local server, "approves" the user and redirects to the app's callback.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import urlencode

import pytest
from playwright.sync_api import Page, expect
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from taskboard.config import Settings
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.providers import IdentityProviders
from taskboard.web import create_app
from tests.e2e.conftest import serve
from tests.fake_idp import FakeIdentityProvider, fake_oidc_provider
from tests.helpers import make_user, section_id


@pytest.fixture
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


@pytest.fixture
def sign_in_as(idp: FakeIdentityProvider) -> Iterator[dict[str, object]]:
    """The provider's sign-in page; tests fill in the claims of the user who signs in there."""
    claims: dict[str, object] = {}

    async def authorize(request: Request) -> RedirectResponse:
        answer = idp.approve(str(request.url), **claims)
        callback = request.query_params["redirect_uri"]
        return RedirectResponse(f"{callback}?{urlencode(answer)}", status_code=302)

    with contextmanager(serve)(Starlette(routes=[Route("/authorize", authorize)])) as base:
        idp.authorization_endpoint = f"{base}authorize"
        yield claims


@pytest.fixture
def sso_server(
    settings: Settings,
    sample_database: Database,
    idp: FakeIdentityProvider,
    sign_in_as: dict[str, object],
) -> Iterator[str]:
    del sign_in_as  # the sign-in page must be up before the app reads the provider's metadata
    with sample_database.new_session(write=True) as s:
        make_user(
            s,
            "jan.peeters",
            display_name="Jan Peeters",
            password=None,
            email="jan.peeters@example.com",
            status=UserStatus.PENDING,
            roles=[(BuiltinRole.EDITOR, Scope.section(section_id(s, "Coatings")))],
        )
    providers = IdentityProviders(redirect={"entra": fake_oidc_provider(idp)})
    yield from serve(create_app(settings, providers=providers))


def test_sign_in_with_microsoft_returns_to_the_same_page(
    sso_server: str, sign_in_as: dict[str, object], page: Page, console_errors: list[str]
) -> None:
    sign_in_as.update(oid="oid-jan", email="jan.peeters@example.com", name="J. Peeters (Quality)")
    page.goto(f"{sso_server}t/130")
    page.locator(".sidebar").get_by_role("button", name="Log in").click()
    page.get_by_role("dialog", name="Log in").get_by_role(
        "link", name="Sign in with Microsoft"
    ).click()
    expect(page).to_have_url(f"{sso_server}t/130")
    # The invited account (matched on email) keeps the name the administrator gave it.
    expect(page.locator(".sidebar__user-name")).to_have_text("Jan Peeters")
    expect(page.locator(".task-panel__key")).to_have_text("T-130")
    expect(page.get_by_role("button", name="Save task")).to_be_visible()  # Editor on Coatings
    assert console_errors == []


def test_a_refused_sign_in_is_explained(
    sso_server: str, sign_in_as: dict[str, object], page: Page
) -> None:
    sign_in_as.update(oid="oid-stranger", email="stranger@example.com")
    page.goto(f"{sso_server}priority")
    page.locator(".sidebar").get_by_role("button", name="Log in").click()
    page.get_by_role("link", name="Sign in with Microsoft").click()
    expect(page.get_by_role("status")).to_contain_text(
        "Sign-in failed: no account has been set up for you"
    )
    expect(page).to_have_url(f"{sso_server}priority")  # the error parameter is tidied away
