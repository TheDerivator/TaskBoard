"""Accessibility (milestone M10): axe-core finds no violations, in the light and the dark theme.

Every view, the dialogs and drawers, and the small-screen navigation are checked with all of
axe's rules (WCAG 2.x A/AA and best practices). Animations are off (reduced motion), so colors
are measured as they end up, not halfway through a fade.
"""

import re
from collections.abc import Iterator

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import Browser, Page, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in

VIEWS = [
    "priority",
    "people",
    "people/STL/Quality",
    "projects",
    "t/104",
    "t/104/conversation",
    "changes/STL/LM",
    "changes/STL/LM/timeline",
    "changes/STL/LM/LM-07",
    "changes/STL/LM/LM-07/conversation",
    "knowledge/STL/CC",
    "knowledge/STL/CC/fm-level",
    "knowledge/STL/LM",
    "fmea/STL/CC",
    "fmea/STL/CC?box=fm-level",
    "fmea/STL/CC?release=v2",
    "cpl/STL",
    "cpl/STL/d-sliver/fm-level?process=CC",
    "cpl/STL/d-blisters?process=LM",
    "cpl/STL/d-sliver?process=CC&release=v3",
    "box/no-such-box",
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

    page.goto(f"{live_server}changes/STL/LM")
    page.get_by_role("link", name="Argon stirring rate during trim").click()
    change = page.get_by_role("dialog", name="Process change LM-07")
    expect(change.get_by_role("button", name="Save change")).to_be_visible()
    assert_accessible(page, "change drawer")
    change.get_by_role("link", name=re.compile("Conversation")).click()
    change.get_by_role("button", name="Period", exact=True).click()
    expect(change.get_by_role("form", name="New period")).to_be_visible()
    assert_accessible(page, "change conversation with the period form")
    change.get_by_role("button", name="Edit period").first.click()
    expect(change.get_by_role("form", name="Edit period")).to_be_visible()
    assert_accessible(page, "editing a period")

    page.goto(f"{live_server}knowledge/STL/CC/mould")
    page.get_by_label("Find in map").fill("powder")
    expect(page.locator(".map-box.is-match")).to_have_count(4)
    assert_accessible(page, "the map while finding")
    page.get_by_role("complementary", name="Selected box").get_by_role(
        "button", name="History"
    ).click()
    expect(page.get_by_role("dialog", name="History of Mould")).to_be_visible()
    assert_accessible(page, "a box's history")

    page.goto(f"{live_server}knowledge/STL/CC/fm-level")
    page.get_by_role("complementary", name="Selected box").get_by_role(
        "button", name="Edit"
    ).click()
    editor = page.get_by_role("region", name="Editing box in Continuous casting")
    expect(editor.get_by_role("button", name="Save box")).to_be_visible()
    assert_accessible(page, "box editor")
    editor.get_by_role("button", name="+ Link to another box (or create one)").click()
    picker = page.get_by_role("dialog", name="Link to another box")
    picker.get_by_label("Find a box by name").fill("mould")
    expect(picker.locator(".box-picker__result").first).to_be_visible()
    assert_accessible(page, "box picker")
    picker.get_by_role("button", name="Close").click()
    editor.get_by_role("button", name="Move", exact=True).click()
    expect(page.get_by_role("dialog", name="Move Mould level fluctuation")).to_be_visible()
    assert_accessible(page, "move dialog")

    page.goto(f"{live_server}knowledge/STL/CC")
    page.get_by_role("button", name="Kinds & links").click()
    settings = page.get_by_role("dialog", name="Kinds & link types")
    settings.get_by_role("button", name="Edit the kind Defect").click()
    expect(settings.get_by_role("form", name="Edit the kind Defect")).to_be_visible()
    assert_accessible(page, "kinds and link types, editing a kind")

    page.goto(f"{live_server}cpl/STL")
    page.get_by_role("button", name="New defect").click()
    expect(page.get_by_role("dialog", name="New defect")).to_be_visible()
    assert_accessible(page, "new defect dialog")
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Edit defect").click()
    defect = page.get_by_role("region", name="Editing box in the STL defect catalogue")
    expect(defect.get_by_role("button", name="Save box")).to_be_visible()
    assert_accessible(page, "defect editor")

    page.goto(f"{live_server}fmea/STL/CC")
    page.get_by_role("button", name="Review & release v4").click()
    expect(page.get_by_role("dialog", name="Release FMEA & control plan v4")).to_be_visible()
    assert_accessible(page, "release dialog")
    page.keyboard.press("Escape")

    page.keyboard.press("Control+k")
    search = page.get_by_role("dialog", name="Search everything")
    search.get_by_role("combobox").fill("mould powder")
    expect(search.get_by_role("option").first).to_be_visible()
    assert_accessible(page, "search everything with results")

    page.goto(f"{live_server}changes/STL/LM")
    page.get_by_role("button", name="New change").click()
    expect(page.get_by_role("button", name="Create change")).to_be_visible()
    assert_accessible(page, "new change drawer")


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

    page.goto(f"{live_server}cpl/STL/d-sliver/fm-level")
    expect(page.get_by_role("complementary", name="How to control it")).to_be_visible()
    assert_accessible(page, "control plan on a phone")
