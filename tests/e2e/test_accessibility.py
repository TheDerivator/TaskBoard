"""Accessibility (milestone M10): axe-core finds no violations, in the light and the dark theme.

Every view, the dialogs and drawers, and the small-screen navigation are checked with all of
axe's rules (WCAG 2.x A/AA and best practices). Animations are off (reduced motion), so colors
are measured as they end up, not halfway through a fade.
"""

from collections.abc import Iterator

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in

VIEWS = [
    "priority",
    "people",
    "projects",
    "t/104",
    "t/104/conversation",
    "admin/users",
    "admin/roles",
    "admin/organization",
    "admin/people",
    "admin/groups",
    "admin/audit",
]


@pytest.fixture(params=["light", "dark"])
def themed(request: pytest.FixtureRequest, browser: Browser) -> Iterator[Page]:
    """A fresh browser (no remembered theme or sidebar state) in the given color scheme."""
    context = browser.new_context(
        color_scheme=request.param,
        reduced_motion="reduce",
        viewport={"width": 1440, "height": 900},
    )
    page = context.new_page()
    page.set_default_timeout(10_000)
    yield page
    context.close()


def assert_accessible(page: Page, where: str) -> None:
    page.wait_for_load_state("networkidle")
    violations = Axe().run(page).response["violations"]
    problems = [
        f"{v['id']} ({v['impact']}) at {node['target']}: "
        f"{(node['any'] or node['all'] or node['none'])[0]['message']}"
        for v in violations
        for node in v["nodes"]
    ]
    assert not problems, f"{where}:\n  " + "\n  ".join(problems)


def test_every_view(live_server: str, themed: Page) -> None:
    page = themed
    page.goto(f"{live_server}priority")
    expect(page.locator(".task-row").first).to_be_visible()
    assert_accessible(page, "priority, as a visitor")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    for path in VIEWS:
        page.goto(f"{live_server}{path}")
        expect(page.locator("#content h1").first).to_be_visible()
        assert_accessible(page, path)


def test_dialogs_and_drawers(live_server: str, themed: Page) -> None:
    page = themed
    page.goto(f"{live_server}priority")
    page.locator(".sidebar").get_by_role("button", name="Log in").click()
    expect(page.get_by_role("dialog", name="Log in")).to_be_visible()
    assert_accessible(page, "login dialog")
    page.keyboard.press("Escape")

    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name="Coating adhesion trial, batch 3").click()
    drawer = page.get_by_role("dialog", name="Task 130")
    expect(drawer.get_by_role("button", name="Save task")).to_be_visible()
    assert_accessible(page, "task drawer")
    drawer.get_by_role("button", name="+ Add to another project").click()
    expect(page.get_by_role("dialog", name="Add to another project")).to_be_visible()
    assert_accessible(page, "placement dialog")

    page.goto(f"{live_server}priority")
    page.get_by_role("button", name="New task").click()
    expect(page.get_by_role("button", name="Create task")).to_be_visible()
    assert_accessible(page, "new task drawer")

    page.goto(f"{live_server}admin/users")
    page.get_by_role("button", name="New account").click()
    expect(page.get_by_role("dialog", name="New account")).to_be_visible()
    assert_accessible(page, "new account dialog")


def test_small_screens_and_the_collapsed_sidebar(live_server: str, themed: Page) -> None:
    page = themed
    page.goto(f"{live_server}people")
    page.get_by_role("button", name="Collapse sidebar").click()
    expect(page.locator(".app")).to_have_class("app is-collapsed")
    assert_accessible(page, "collapsed sidebar")

    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server}priority")
    page.get_by_role("button", name="Open navigation").click()
    expect(page.get_by_role("link", name="People")).to_be_visible()
    assert_accessible(page, "phone navigation")
