"""Releases in a browser (milestone M18): the release bar, blue dots, releasing, old versions."""

import re

import pytest
from playwright.sync_api import Locator, Page, expect
from sqlalchemy import select

from taskboard.db.models import Department
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.e2e.conftest import log_in
from tests.helpers import PASSWORD, make_user


@pytest.fixture
def stl_editor(sample_database: Database) -> None:
    with sample_database.new_session(write=True) as s:
        stl = s.scalars(select(Department.id).where(Department.code == "STL")).one()
        make_user(s, "editor", roles=[(BuiltinRole.EDITOR, Scope.department(stl))])


def _bar(page: Page) -> Locator:
    return page.get_by_role("group", name="Released versions")


def test_the_draft_since_v3_is_marked(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}fmea/STL/CC?box=fm-level")
    bar = _bar(page)
    expect(bar.locator(".release-bar__version")).to_have_text("FMEA v3")
    expect(bar).to_contain_text("Released 12 Sep 2026 · Anna Claes")
    expect(bar).to_contain_text("Draft: 4 changes since v3")
    expect(bar.get_by_role("button", name=re.compile("Review & release"))).to_have_count(0)
    expect(page.locator(".map-box__draft")).to_have_count(4)
    panel = page.get_by_role("complementary", name="Selected box")
    expect(panel.locator(".draft-pill")).to_have_text("Control changed since v3")


def test_releasing_v4_and_looking_back_at_v3(
    stl_editor: None, live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    page.goto(f"{live_server}fmea/STL/CC")
    _bar(page).get_by_role("button", name="Review & release v4").click()
    dialog = page.get_by_role("dialog", name="Release FMEA & control plan v4")
    changes = dialog.locator(".release-change")
    expect(changes).to_have_count(4)
    expect(changes.last).to_contain_text("No controls yet")
    expect(dialog).to_contain_text("4 affect FMEA, 3 affect CPL")
    dialog.get_by_label("Release note").fill("Spray cooling failure mode added.")
    dialog.get_by_role("button", name="Release v4").click()
    expect(dialog).to_have_count(0)
    bar = _bar(page)
    expect(bar.locator(".release-bar__version")).to_have_text("FMEA v4")
    expect(bar).to_contain_text("No changes since v4")
    expect(page.locator(".map-box__draft")).to_have_count(0)

    bar.get_by_label("Viewing").select_option(value="v3")
    expect(page).to_have_url(re.compile(r"fmea/STL/CC\?release=v3$"))
    expect(bar).to_contain_text("Earlier version: After mould powder change CC-31")
    expect(page.locator('.map-box[data-box="fm-burr"]')).to_be_visible()
    expect(page.locator('.map-box[data-box="fm-spray"]')).to_have_count(0)  # came after v3
    panel = page.get_by_role("complementary", name="Selected box")
    expect(panel.get_by_role("button", name="Edit")).to_have_count(0)  # versions are read only
    assert console_errors == []


def test_the_control_plan_of_a_release(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}cpl/STL?process=CC")
    bar = _bar(page)
    expect(bar.locator(".release-bar__version")).to_have_text("CPL v3")
    defects = page.get_by_role("navigation", name="Defects")
    expect(defects.get_by_role("link", name=re.compile("Corner cracks"))).to_be_visible()
    bar.get_by_label("Viewing").select_option(value="v3")
    expect(page).to_have_url(re.compile(r"cpl/STL\?process=CC&release=v3$"))
    expect(defects.get_by_role("link", name=re.compile("Corner cracks"))).to_have_count(0)
    page.get_by_role("navigation", name="Process").get_by_role("link", name="All processes").click()
    expect(page).to_have_url(re.compile(r"cpl/STL$"))  # all processes: no versions (A18)
    expect(_bar(page)).to_have_count(0)


def test_printing_an_old_version(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}fmea/STL/CC?release=v2")
    expect(_bar(page).locator(".release-bar__version")).to_have_text("FMEA v2")
    page.emulate_media(media="print")
    sheet = page.locator(".print-sheet")
    expect(sheet.locator(".print-sheet__head")).to_contain_text("v2, released 3 Mar 2026")
    expect(sheet.locator("tbody tr")).to_have_count(7)  # no spray cooling yet
