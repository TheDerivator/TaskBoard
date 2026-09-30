"""Windows sign-in in a real browser: Chromium answers the Negotiate challenge through SSPI.

Windows only, and nothing is faked: the browser proves to the app (over NTLM, to 127.0.0.1) that
it runs as whoever runs the tests, in two requests on one connection to a real Uvicorn.
"""

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import BrowserType, Locator, Page, expect

from taskboard.config import Settings, UnknownUserPolicy
from taskboard.db.session import Database
from taskboard.web import create_app
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in, serve

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="needs Windows SSPI")


def _serve(settings: Settings, **overrides: object) -> Iterator[str]:
    # Whoever runs the tests has no account here: let the first sign-in create one.
    settings = settings.model_copy(
        update={"windows_auth": True, "sso_unknown_users": UnknownUserPolicy.CREATE} | overrides
    )
    yield from serve(create_app(settings))  # the provider comes from the settings: real SSPI


@pytest.fixture
def windows_server(settings: Settings, sample_database: Database) -> Iterator[str]:
    del sample_database  # loaded before the server starts
    yield from _serve(settings)


@pytest.fixture
def windows_page(
    browser_type: BrowserType, browser_type_launch_args: dict[str, Any], tmp_path: Path
) -> Iterator[Page]:
    """A page in a browser that signs in to 127.0.0.1 with the Windows login, as an intranet
    zone or the AuthServerAllowlist policy arranges for real users.

    Chromium never does that from the incognito-like contexts Playwright normally uses, hence a
    browser with a profile of its own.
    """
    context = browser_type.launch_persistent_context(
        tmp_path / "profile",
        **{**browser_type_launch_args, "args": ["--auth-server-allowlist=127.0.0.1"]},
    )
    context.set_default_timeout(10_000)
    yield context.pages[0] if context.pages else context.new_page()
    context.close()


def log_in_button(page: Page) -> Locator:
    return page.locator(".sidebar").get_by_role("button", name="Log in")


def windows_login() -> str:
    """The login name Windows gives whoever runs the tests (the `jdoe` of `CORP\\jdoe`)."""
    import spnego

    client = spnego.client(hostname="localhost", service="HTTP")
    server = spnego.server()
    token = client.step()
    while token and not server.complete:
        answer = server.step(token)
        token = client.step(answer) if answer and not client.complete else None
    return (server.client_principal or "").rsplit("\\", 1)[-1].lower()


def test_a_visitor_is_signed_in_without_doing_anything(
    windows_server: str, windows_page: Page
) -> None:
    page = windows_page
    page.goto(f"{windows_server}t/104")
    expect(page.get_by_role("button", name="Log out")).to_be_visible()
    expect(log_in_button(page)).to_have_count(0)
    expect(page).to_have_url(f"{windows_server}t/104")  # no redirects: the page stayed put
    expect(page.locator(".task-panel__key")).to_have_text("T-104")


def test_logging_out_lasts_and_the_admin_account_still_works(
    windows_server: str, windows_page: Page
) -> None:
    page = windows_page
    page.goto(f"{windows_server}priority")
    page.get_by_role("button", name="Log out").click()
    expect(log_in_button(page)).to_be_visible()
    page.reload()  # not signed in again behind the user's back
    expect(log_in_button(page)).to_be_visible()

    log_in(page, "admin", TEST_ADMIN_PASSWORD)  # the break-glass account
    expect(page.locator(".sidebar__user-name")).to_have_text("Administrator")
    page.get_by_role("button", name="Log out").click()

    log_in_button(page).click()
    page.get_by_role("dialog", name="Log in").get_by_role(
        "button", name="Sign in with Windows"
    ).click()
    expect(page.get_by_role("button", name="Log out")).to_be_visible()
    expect(page.locator(".sidebar__user-name")).not_to_have_text("Administrator")


def test_the_guides_first_steps_refused_then_prepared_then_signed_in(
    settings: Settings, sample_database: Database, windows_page: Page
) -> None:
    """docs/WINDOWS-SIGNIN.md, "Start with yourself", on an invite-only board."""
    del sample_database
    page = windows_page
    for base in _serve(settings, sso_unknown_users=UnknownUserPolicy.REJECT):
        page.goto(f"{base}priority")
        expect(page.get_by_role("status")).to_contain_text(
            "Windows sign-in: no account has been set up for you"
        )
        expect(page.locator(".task-row")).to_have_count(10)  # still a visitor like any other

        log_in(page, "admin", TEST_ADMIN_PASSWORD)
        page.get_by_role("link", name="Administration").click()
        page.get_by_role("button", name="New account").click()
        dialog = page.get_by_role("dialog", name="New account")
        dialog.get_by_label("Username").fill(windows_login())
        dialog.get_by_label("Display name").fill("Me Myself")
        dialog.get_by_label("SSO only (pre-provisioned)").check()  # and no email
        dialog.get_by_label("Initial role (optional)").select_option(label="Administrator")
        dialog.get_by_role("button", name="Create account").click()
        dialog.get_by_role("button", name="Done").click()
        page.get_by_role("button", name="Log out").click()

        log_in_button(page).click()
        page.get_by_role("button", name="Sign in with Windows").click()
        expect(page.locator(".sidebar__user-name")).to_have_text("Me Myself")
        expect(page.get_by_role("link", name="Administration")).to_be_visible()

        page.reload()  # and from now on without being asked: here, from the session
        expect(page.locator(".sidebar__user-name")).to_have_text("Me Myself")


def test_with_automatic_sign_in_off_it_takes_a_click(
    settings: Settings, sample_database: Database, windows_page: Page
) -> None:
    del sample_database
    page = windows_page
    for base in _serve(settings, windows_auth_automatic=False):
        page.goto(f"{base}priority")
        expect(page.locator(".task-row")).to_have_count(10)
        expect(log_in_button(page)).to_be_visible()
        log_in_button(page).click()
        page.get_by_role("button", name="Sign in with Windows").click()
        expect(page.get_by_role("button", name="Log out")).to_be_visible()


def test_a_browser_that_does_not_answer_leaves_the_visitor_anonymous(
    windows_server: str, page: Page, console_errors: list[str]
) -> None:
    """Playwright's ordinary (incognito-like) page: Chromium keeps the Windows login to itself."""
    page.goto(f"{windows_server}priority")
    expect(page.locator(".task-row")).to_have_count(10)  # the board, as any visitor sees it
    expect(log_in_button(page)).to_be_visible()
    log_in_button(page).click()
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_role("button", name="Sign in with Windows").click()
    expect(dialog.get_by_role("alert")).to_contain_text("did not work in this browser")
    assert console_errors == []
