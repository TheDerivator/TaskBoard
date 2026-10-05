"""Process changes and Process knowledge in a real browser (M11): navigation and rights."""

import re

from playwright.sync_api import Page, expect

from taskboard.db.session import Database
from taskboard.domain.access import Permission, Scope
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in
from tests.helpers import PASSWORD, make_role, make_user, revoke_anonymous_access, section_id


def _heading(page: Page) -> str:
    return page.locator("#content h1").first.inner_text()


def test_the_sidebar_leads_to_both_modules_which_share_the_process(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    sidebar = page.locator(".sidebar")
    sidebar.get_by_role("link", name="Process changes").click()
    expect(page).to_have_url(f"{live_server}changes/STL/CV")
    expect(page.locator("#content h1")).to_have_text("Convertor")

    page.get_by_role("navigation", name="Process").get_by_role(
        "link", name="Continuous casting"
    ).click()
    expect(page).to_have_url(f"{live_server}changes/STL/CC")
    page.get_by_role("navigation", name="View").get_by_role("link", name="Timeline").click()
    expect(page).to_have_url(f"{live_server}changes/STL/CC/timeline")

    # The process chosen last is shared with Process knowledge (DESIGN open question 4).
    sidebar.get_by_role("link", name="Process knowledge").click()
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC")
    expect(page.locator("#content h1")).to_have_text("Continuous casting")
    page.get_by_role("navigation", name="View").get_by_role("link", name="FMEA").click()
    expect(page).to_have_url(f"{live_server}fmea/STL/CC")
    page.get_by_role("navigation", name="View").get_by_role("link", name="CPL").click()
    expect(page).to_have_url(f"{live_server}cpl/STL?process=CC")
    assert console_errors == []


def test_links_are_forgiving_about_case_and_say_when_a_process_does_not_exist(
    live_server: str, page: Page
) -> None:
    page.goto(f"{live_server}changes/stl/lm")
    expect(page).to_have_url(f"{live_server}changes/STL/LM")
    expect(page.locator("#content h1")).to_have_text("Ladle metallurgy")
    page.goto(f"{live_server}knowledge/STL/NOPE")
    expect(page.locator("#content h1")).to_have_text("This process does not exist")


def test_someone_who_may_only_read_process_knowledge(
    live_server: str, page: Page, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as s:
        revoke_anonymous_access(s)
        make_role(s, "map-reader", [Permission.KNOWLEDGE_VIEW])
        process = section_id(s, "Process")
        make_user(s, "reader", roles=[("map-reader", Scope.section(process))])
    page.goto(live_server)
    expect(page.locator("#content h1")).to_have_text("Log in to see the board")
    log_in(page, "reader", PASSWORD)
    page.goto(live_server)
    expect(page).to_have_url(re.compile(r"knowledge/STL/CV$"))
    sidebar = page.locator(".sidebar")
    expect(sidebar.get_by_role("link", name="Process knowledge")).to_be_visible()
    expect(sidebar.get_by_role("link", name="Priority")).to_have_count(0)
    expect(sidebar.get_by_role("link", name="Process changes")).to_have_count(0)
    page.goto(f"{live_server}changes/STL/LM")
    expect(page.locator("#content h1")).to_have_text("No access yet")


def test_an_administrator_adds_a_process(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.goto(f"{live_server}admin/organization")
    page.get_by_label("New process code in STL").fill("hm")
    page.get_by_label("New process name in STL").fill("Hot metal")
    page.get_by_label("Owning section of the new process in STL").select_option(
        label="STL · Process"
    )
    page.get_by_role("button", name="Add process").first.click()
    expect(page.get_by_label("Name of process HM")).to_have_value("Hot metal")

    page.locator(".sidebar").get_by_role("link", name="Process changes").click()
    tabs = page.get_by_role("navigation", name="Process")
    tabs.get_by_role("link", name="Hot metal").click()
    expect(page).to_have_url(f"{live_server}changes/STL/HM")
    assert _heading(page) == "Hot metal"
