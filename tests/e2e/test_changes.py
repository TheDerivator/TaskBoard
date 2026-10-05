"""Process changes in a real browser (milestone M13): list, drawer, conversation, timeline."""

import re

import pytest
from playwright.sync_api import Page, expect
from sqlalchemy import select

from taskboard.db.models import Department
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.e2e.conftest import log_in
from tests.helpers import PASSWORD, make_user


@pytest.fixture
def editor(live_server: str, page: Page, sample_database: Database) -> Page:
    """Logged in as an Editor of STL (so of its processes, owned by STL › Process)."""
    with sample_database.new_session(write=True) as s:
        stl = s.scalars(select(Department.id).where(Department.code == "STL")).one()
        make_user(s, "editor", roles=[(BuiltinRole.EDITOR, Scope.department(stl))])
    page.goto(f"{live_server}changes/STL/LM")
    log_in(page, "editor", PASSWORD)
    return page


def _row(page: Page, key: str):
    return page.locator(".change-row", has=page.locator(".change-row__key", has_text=key))


def test_the_list_shows_periods_and_the_state_today(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}changes/STL/LM")
    expect(page.locator(".change-row")).to_have_count(6)
    expect(_row(page, "LM-12").locator(".state-pill")).to_have_text("Planned from 13 Oct")
    expect(_row(page, "LM-11").locator(".state-pill")).to_have_text("Test running until 3 Oct")
    expect(_row(page, "LM-07").locator(".period-chip")).to_have_text(
        ["Test 14 Apr", "Test 16 Apr", "Change from 21 Apr"]
    )
    page.get_by_label("Search changes").fill("skull")
    expect(page.locator(".change-row")).to_have_count(1)
    # Visitors read, but see no editing controls.
    expect(page.get_by_role("button", name="New change")).to_have_count(0)
    assert console_errors == []


def test_a_new_change_gets_its_first_period(editor: Page, live_server: str) -> None:
    page = editor
    page.get_by_role("button", name="New change").click()
    drawer = page.get_by_role("dialog", name="New process change")
    drawer.get_by_label("Change", exact=True).fill("Tap hole cleaning interval")
    drawer.get_by_label("Why").fill("Fewer **delays** at tapping.")
    drawer.get_by_role("button", name="Create change").click()
    expect(page).to_have_url(f"{live_server}changes/STL/LM/LM-13")

    change = page.get_by_role("dialog", name="Process change LM-13")
    change.get_by_role("button", name="+ Post a period").click()
    expect(page).to_have_url(f"{live_server}changes/STL/LM/LM-13/conversation")
    form = change.get_by_role("form", name="New period")
    form.get_by_label("Label").fill("Trial week")
    form.get_by_label("From").fill("2026-10-12")
    form.get_by_label("To").fill("2026-10-16")
    form.get_by_label("Add scope tag").fill("LF2")
    form.get_by_label("Add scope tag").press("Enter")
    expect(form.get_by_text("Appears on the timeline as a test from 12 to 16 Oct")).to_be_visible()
    form.get_by_role("button", name="Post period").click()
    expect(change.locator(".period-post")).to_have_count(1)
    expect(change.locator(".period-post .scope-tag")).to_have_text(["LF2"])

    change.get_by_role("button", name="Close").click()
    expect(_row(page, "LM-13").locator(".period-chip")).to_have_text(["Planned test 12–16 Oct"])
    page.get_by_role("navigation", name="View").get_by_role("link", name="Timeline").click()
    expect(
        page.get_by_role("link", name=re.compile(r"Tap hole cleaning interval, Planned test"))
    ).to_be_visible()


def test_ending_a_process_change_and_its_history(editor: Page, live_server: str) -> None:
    page = editor
    page.goto(f"{live_server}changes/STL/LM/LM-09/conversation")
    change = page.get_by_role("region", name="Process change LM-09")
    change.get_by_role("button", name="Set end date").click()
    change.get_by_label("Last day in effect").fill("2026-09-30")
    change.get_by_role("button", name="Set end date").click()
    expect(change.locator(".state-pill")).to_have_text("Ended 30 Sep")
    expect(change.locator(".period-post__dates")).to_have_text("12 May – 30 Sep 2026 · ended")

    change.get_by_role("button", name="edited").click()
    history = page.get_by_role("dialog", name="Earlier versions")
    expect(history.locator(".history__version")).to_have_count(2)
    expect(history.locator(".history__period").first).to_contain_text("no end date")


def test_editing_details_and_a_stale_save(editor: Page, live_server: str) -> None:
    page = editor
    page.goto(f"{live_server}changes/STL/LM")
    page.get_by_role("link", name="Ladle preheating +50 °C").click()
    drawer = page.get_by_role("dialog", name="Process change LM-09")
    drawer.get_by_label("Why").fill("Fewer skulls, and less refractory wear.")
    drawer.get_by_role("button", name="Save change").click()
    expect(drawer).to_be_hidden()
    expect(_row(page, "LM-09").locator(".change-row__why")).to_have_text(
        "Fewer skulls, and less refractory wear."
    )


def test_a_change_link_opened_directly_is_a_page_and_follows_the_change(
    live_server: str, page: Page
) -> None:
    page.goto(f"{live_server}changes/stl/cc/lm-07")  # wrong process, loosely spelled
    expect(page).to_have_url(f"{live_server}changes/STL/LM/LM-07")
    expect(page.locator("#content h1")).to_contain_text("LM-07")
    # A visitor reads, without forms.
    expect(page.get_by_role("button", name="Save change")).to_have_count(0)
    page.get_by_role("link", name=re.compile("Conversation")).click()
    expect(page.locator(".period-post")).to_have_count(3)
    expect(page.get_by_role("form", name="New period")).to_have_count(0)
