"""The knowledge map in a real browser (M15): the map, the panel, finding, the keyboard."""

import re

from playwright.sync_api import Locator, Page, expect
from sqlalchemy import select

from taskboard.db.models import Department
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.e2e.conftest import log_in
from tests.helpers import PASSWORD, make_user


def _box(page: Page, key: str) -> Locator:
    return page.locator(f'.map-box[data-box="{key}"]')


def _panel(page: Page) -> Locator:
    return page.get_by_role("complementary", name="Selected box")


def test_a_box_opened_by_its_link(live_server: str, page: Page, console_errors: list[str]) -> None:
    page.goto(f"{live_server}knowledge/STL/CC/fm-level")
    panel = _panel(page)
    expect(panel.get_by_role("heading", name="Mould level fluctuation")).to_be_visible()
    path = "Continuous casting › Mould › Mould level control"
    expect(panel.locator(".box-panel__path")).to_have_text(path)
    expect(panel.locator(".control-tag")).to_have_text(["Prevent", "Prevent", "Detect"])
    leads_to = panel.locator(
        ".box-panel__section", has=page.get_by_role("heading", name="Leads to")
    )
    expect(leads_to.locator(".rel-chip")).to_have_text(["Sliver lines", "Longitudinal cracks"])
    expect(panel.locator(".ext-link__label")).to_have_text(
        ["Mould level – live", "Eddy-current level sensor", "Level fluctuation vs. sliver rate"]
    )
    expect(panel.get_by_role("link", name=re.compile("T-104"))).to_be_visible()
    expect(_box(page, "fm-level")).to_have_class(re.compile("is-selected"))
    expect(_box(page, "fm-level").locator(".effect-chip")).to_have_text(
        ["→ Sliver lines", "→ Longitudinal cracks"]
    )
    assert console_errors == []


def test_collapsing_and_expanding_branches(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}knowledge/STL/CC/fm-level")
    expect(_box(page, "m-level")).to_be_visible()
    expect(_box(page, "tun-flow")).to_have_count(0)  # an overview: other branches start closed
    page.get_by_role("button", name="Collapse Mould", exact=True).click()
    expect(_box(page, "m-level")).to_have_count(0)
    expect(_box(page, "mould").locator(".map-box__badge")).to_have_text("2")  # rolled up
    page.get_by_role("button", name="Expand Mould", exact=True).click()
    expect(_box(page, "m-level")).to_be_visible()
    page.get_by_role("button", name="Expand all").click()
    expect(_box(page, "fm-burr")).to_be_visible()
    page.get_by_role("group", name="Show kinds").get_by_role("button", name="Rule").click()
    expect(_box(page, "plan")).to_have_count(0)


def test_moving_through_the_map(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}knowledge/STL/CC/fm-level")
    _panel(page).get_by_role("button", name="Nozzle clogging").click()  # a link chip
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC/fm-clog")
    expect(_box(page, "fm-clog")).to_be_visible()  # its closed branch opened
    _box(page, "fm-clog").locator(".map-box__main").focus()
    page.keyboard.press("ArrowLeft")
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC/tun-flow")
    expect(_box(page, "tun-flow").locator(".map-box__main")).to_be_focused()
    page.keyboard.press("Home")
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC/cc")
    expect(_panel(page).get_by_role("heading", name="Continuous casting")).to_be_visible()


def test_the_changes_in_a_branch_and_the_history(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}knowledge/STL/CC/mould")
    panel = _panel(page)
    changes = panel.locator(".related-change")
    expect(changes).to_have_count(2)
    expect(changes.first).to_contain_text("CC-31")
    expect(changes.first).to_contain_text("on Mould powder")
    panel.get_by_role("button", name="History").click()
    history = page.get_by_role("dialog", name="History of Mould")
    expect(history.locator(".revision-list li")).to_have_count(1)
    expect(history).to_contain_text("Created")


def test_finding_in_the_map(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}knowledge/STL/CC")
    page.get_by_label("Find in map").fill("powder")
    expect(page.get_by_text("4 matches")).to_be_visible()
    expect(page.locator(".map-box.is-match")).to_have_count(4)
    expect(_box(page, "ref-powder")).to_be_visible()


def test_starting_a_map(live_server: str, page: Page, sample_database: Database) -> None:
    page.goto(f"{live_server}knowledge/STL/LM")
    expect(page.get_by_role("heading", name="No map for Ladle metallurgy yet")).to_be_visible()
    expect(page.get_by_role("button", name="Start the map")).to_have_count(0)  # visitors only read
    with sample_database.new_session(write=True) as s:
        stl = s.scalars(select(Department.id).where(Department.code == "STL")).one()
        make_user(s, "editor", roles=[(BuiltinRole.EDITOR, Scope.department(stl))])
    log_in(page, "editor", PASSWORD)
    page.get_by_role("button", name="Start the map").click()
    expect(_box(page, "ladle-metallurgy")).to_be_visible()
