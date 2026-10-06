"""The FMEA and the control plan in a browser (milestone M17): filtering, causes, controls,
defects, and the printed sheets."""

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


def _box(page: Page, key: str) -> Locator:
    return page.locator(f'.map-box[data-box="{key}"]')


def _defects(page: Page) -> Locator:
    return page.get_by_role("navigation", name="Defects")


def _diagram(page: Page) -> Locator:
    return page.get_by_role("region", name="How it arises")


def _control(page: Page) -> Locator:
    return page.get_by_role("complementary", name="How to control it")


def test_the_fmea_shows_failure_modes_and_the_steps_to_them(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}fmea/STL/CC?box=fm-level")
    views = page.get_by_role("navigation", name="View")
    expect(views.get_by_role("link", name="FMEA")).to_have_attribute("aria-current", "page")
    expect(_box(page, "fm-burr")).to_be_visible()  # it opens fully
    expect(_box(page, "overview")).to_have_count(0)
    expect(_box(page, "ref-powder")).to_have_count(0)
    expect(_box(page, "fm-level")).to_have_class(re.compile("is-selected"))
    panel = page.get_by_role("complementary", name="Selected box")
    expect(panel.locator(".control-tag")).to_have_text(["Prevent", "Prevent", "Detect"])
    _box(page, "fm-powder").locator(".map-box__main").click()
    expect(page).to_have_url(re.compile(r"fmea/STL/CC\?box=fm-powder$"))
    page.get_by_role("searchbox", name="Find in map").fill("caster")  # the overview is not here
    expect(page.get_by_text("0 matches")).to_be_visible()
    assert console_errors == []


def test_printing_the_fmea(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}fmea/STL/CC")
    expect(_box(page, "fm-burr")).to_be_visible()
    page.emulate_media(media="print")
    sheet = page.locator(".print-sheet")
    expect(sheet.get_by_role("heading", name="FMEA · Continuous casting")).to_be_visible()
    rows = sheet.locator("tbody tr")
    expect(rows).to_have_count(8)
    expect(rows.first).to_contain_text("Tundish › Flow control")
    expect(rows.first).to_contain_text("Nozzle clogging")
    expect(rows.nth(2)).to_contain_text(
        "Mould level – live: https://grafana.plant.local/d/mould-level"
    )
    expect(page.locator(".map")).to_be_hidden()
    expect(page.locator(".sidebar")).to_be_hidden()


def test_the_control_plan_from_defect_to_controls(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}cpl/STL")
    expect(page.get_by_role("heading", level=1, name="Sliver lines")).to_be_visible()
    expect(_defects(page).locator(".cpl-defect")).to_have_count(7)
    sliver = _defects(page).get_by_role("link", name=re.compile("Sliver lines"))
    expect(sliver).to_have_attribute("aria-current", "page")
    diagram = _diagram(page)
    expect(diagram.locator(".cpl-node--where .cpl-node__label")).to_have_text(["Tundish", "Mould"])
    expect(diagram.locator(".cpl-node--cause .cpl-node__label")).to_have_text(
        ["Nozzle clogging", "Slag carry-over", "Mould level fluctuation", "Powder entrapment"]
    )
    control = _control(page)
    expect(control.get_by_role("heading", name="Nozzle clogging")).to_be_visible()
    expect(control.get_by_role("heading", name="How it leads to sliver lines")).to_be_visible()

    diagram.get_by_role("link", name=re.compile("Mould level fluctuation")).click()
    expect(page).to_have_url(re.compile(r"cpl/STL/d-sliver/fm-level$"))
    expect(control).to_contain_text("Meniscus waves fold powder into the shell as it forms.")
    expect(control.locator(".control-tag")).to_have_text(["Prevent", "Prevent", "Detect"])
    expect(control.locator(".ext-link__label")).to_have_text(
        ["Mould level – live", "Eddy-current level sensor", "Level fluctuation vs. sliver rate"]
    )
    expect(control.get_by_role("link", name=re.compile("T-104"))).to_be_visible()  # related

    _defects(page).get_by_role("link", name=re.compile("Transverse cracks")).click()
    expect(diagram.locator(".cpl-node--cause")).to_have_count(2)
    expect(control).to_contain_text("No controls documented for this cause yet.")
    control.get_by_role("link", name="Show in knowledge map").click()
    expect(page).to_have_url(re.compile(r"knowledge/STL/CC/fm-osc$"))
    assert console_errors == []


def test_the_control_plan_of_one_process(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}cpl")
    expect(page).to_have_url(re.compile(r"cpl/STL$"))  # the department of the first process
    tabs = page.get_by_role("navigation", name="Process")
    expect(tabs.get_by_role("link", name="All processes")).to_have_attribute("aria-current", "page")
    _defects(page).get_by_role("link", name=re.compile("Blisters")).click()
    tabs.get_by_role("link", name="Ladle metallurgy").click()
    expect(page).to_have_url(re.compile(r"cpl/STL/d-blisters\?process=LM$"))
    # Every defect stays listed (D-096), even with no causes in this process.
    expect(_defects(page).locator(".cpl-defect")).to_have_count(7)
    expect(_defects(page).locator(".cpl-defect__count")).to_have_text(
        [re.compile(r"known causes: 0$")] * 7
    )
    expect(_diagram(page)).to_contain_text("No known causes in Ladle metallurgy yet.")
    tabs.get_by_role("link", name="Continuous casting").click()
    expect(_defects(page).locator(".cpl-defect")).to_have_count(7)
    expect(_diagram(page).locator(".cpl-node--cause")).to_have_text(
        [re.compile("Powder entrapment")]
    )


def test_a_new_defect_and_its_description(stl_editor: None, live_server: str, page: Page) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    page.goto(f"{live_server}cpl/STL")
    page.get_by_role("button", name="New defect").click()
    dialog = page.get_by_role("dialog", name="New defect")
    dialog.get_by_label("Name").fill("Scale pits")
    dialog.get_by_label("Group").fill("Surface")
    expect(dialog.get_by_label("Section that owns it")).to_have_value(re.compile(r"\d+"))
    dialog.get_by_role("button", name="Add defect").click()
    expect(page).to_have_url(re.compile(r"cpl/STL/scale-pits$"))
    expect(page.get_by_role("heading", level=1, name="Scale pits")).to_be_visible()
    surface = _defects(page).locator(
        ".cpl-defects__group", has=page.get_by_role("heading", name="Surface")
    )
    expect(surface.locator(".cpl-defect__name")).to_have_text(
        ["Sliver lines", "Blisters", "Scale pits"]
    )

    page.get_by_role("button", name="Edit defect").click()
    editor = page.get_by_role("region", name="Editing box in the STL defect catalogue")
    editor.get_by_role("textbox", name="Description").fill("Small pits from rolled-in **scale**.")
    editor.get_by_role("button", name="Save box").click()
    expect(editor).to_have_count(0)
    expect(page.locator(".cpl-description")).to_have_text("Small pits from rolled-in scale.")


def test_printing_the_control_plan(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}cpl/STL?process=CC")
    expect(_diagram(page)).to_be_visible()
    page.emulate_media(media="print")
    sheet = page.locator(".print-sheet")
    expect(sheet.get_by_role("heading", level=1)).to_contain_text("Control plan")
    expect(sheet).to_contain_text("Continuous casting")
    defects = sheet.locator(".print-sheet__defect")
    expect(defects).to_have_count(7)
    expect(defects.first.locator("tbody tr")).to_have_count(4)
    expect(defects.first).to_contain_text("Meniscus waves fold powder into the shell as it forms.")
    expect(page.locator(".cpl")).to_be_hidden()
