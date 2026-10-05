"""Editing the knowledge map in a browser (milestone M16): boxes, links, settings, references."""

import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect
from sqlalchemy import select

from taskboard.db.models import Department
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in
from tests.helpers import PASSWORD, make_user


@pytest.fixture
def editors(sample_database: Database) -> None:
    """Two editors of STL (its processes' maps and its defects)."""
    with sample_database.new_session(write=True) as s:
        stl = s.scalars(select(Department.id).where(Department.code == "STL")).one()
        for name in ("editor", "second"):
            make_user(s, name, roles=[(BuiltinRole.EDITOR, Scope.department(stl))])


def _panel(page: Page) -> Locator:
    return page.get_by_role("complementary", name="Selected box")


def _editor(page: Page) -> Locator:
    return page.get_by_role(
        "region", name=re.compile(r"(Editing box|New box) in Continuous casting")
    )


def _open_editor(page: Page, live_server: str, key: str) -> Locator:
    page.goto(f"{live_server}knowledge/STL/CC/{key}")
    _panel(page).get_by_role("button", name="Edit").click()
    editor = _editor(page)
    expect(editor.get_by_role("button", name="Save box")).to_be_visible()
    return editor


def test_editing_a_box_writes_a_revision(editors: None, live_server: str, page: Page) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    editor = _open_editor(page, live_server, "fm-level")
    editor.get_by_role("textbox", name="Description").fill("Waves at the **meniscus**.")
    editor.get_by_label("Control 3", exact=True).fill("Alarm above [NEW LIMIT] mm fluctuation")
    editor.get_by_role("button", name="+ External link").click()
    editor.get_by_label("Label").fill("Meniscus camera")
    editor.get_by_label("URL").fill("https://grafana.plant.local/d/meniscus")
    editor.get_by_label("Pass this box as a parameter").check()
    editor.get_by_role("button", name="Add link").click()
    editor.get_by_role("button", name="Save box").click()
    expect(editor).to_have_count(0)

    panel = _panel(page)
    expect(panel.locator(".md")).to_have_text("Waves at the meniscus.")
    expect(panel.get_by_text("Alarm above [NEW LIMIT] mm fluctuation")).to_be_visible()
    meniscus = panel.get_by_role("link", name=re.compile("Meniscus camera"))
    expect(meniscus).to_have_attribute(
        "href", "https://grafana.plant.local/d/meniscus?node=fm-level"
    )
    panel.get_by_role("button", name="History").click()
    history = page.get_by_role("dialog", name="History of Mould level fluctuation")
    expect(history.locator(".revision-list li").first).to_contain_text("Changed")
    expect(history).to_contain_text(
        "Changed detect control: Alarm above [NEW LIMIT] mm fluctuation"
    )


def test_the_second_of_two_editors_gets_a_conflict(
    editors: None, live_server: str, page: Page, browser: Browser
) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    other = browser.new_context().new_page()
    other.goto(live_server)
    log_in(other, "second", PASSWORD)
    first = _open_editor(page, live_server, "mould")
    second = _open_editor(other, live_server, "mould")
    first.get_by_role("textbox", name="Description").fill("First version.")
    first.get_by_role("button", name="Save box").click()
    expect(first).to_have_count(0)
    second.get_by_role("textbox", name="Description").fill("Second version.")
    second.get_by_role("button", name="Save box").click()
    expect(second.get_by_role("alert")).to_contain_text("Someone else changed this box")
    other.context.close()


def test_adding_moving_and_deleting_boxes(editors: None, live_server: str, page: Page) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    page.goto(f"{live_server}knowledge/STL/CC/m-level")
    _panel(page).get_by_role("button", name="+ Add a box under this").click()
    editor = _editor(page)
    editor.get_by_label("Kind").select_option(label="Knowledge")
    editor.get_by_label("Name").fill("Level sensor principle")
    editor.get_by_role("button", name="Create box").click()
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC/level-sensor-principle")
    expect(page.locator('.map-box[data-box="level-sensor-principle"]')).to_be_visible()

    editor = _open_editor(page, live_server, "level-sensor-principle")
    editor.get_by_role("button", name="Move", exact=True).click()
    move = page.get_by_role("dialog", name="Move Level sensor principle")
    move.get_by_role("radio", name="Oscillation", exact=True).check()
    move.get_by_role("button", name="Move", exact=True).click()
    expect(_panel(page).locator(".box-panel__path")).to_have_text(
        "Continuous casting › Mould › Oscillation"
    )

    editor = _open_editor(page, live_server, "level-sensor-principle")
    page.once("dialog", lambda d: d.accept())
    editor.get_by_role("button", name="Delete").click()
    expect(page.locator('.map-box[data-box="level-sensor-principle"]')).to_have_count(0)


def test_a_change_linked_into_the_map_rolls_up_and_filters_the_timeline(
    editors: None, live_server: str, page: Page
) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    page.goto(f"{live_server}changes/STL/LM/LM-07")  # opened directly: the change's own page
    drawer = page.get_by_role("region", name="Process change LM-07")
    drawer.get_by_role("button", name="+ Link to a box").click()
    picker = page.get_by_role("dialog", name="Link to a box")
    picker.get_by_label("Find a box by name").fill("powder entr")
    picker.get_by_role("button", name=re.compile("Powder entrapment")).click()
    expect(drawer.locator(".box-link")).to_contain_text(
        "Continuous casting › Mould › Mould powder › Powder entrapment"
    )

    page.goto(f"{live_server}knowledge/STL/CC/mould")
    expect(_panel(page).locator(".related-change", has_text="LM-07")).to_contain_text(
        "on Powder entrapment"
    )
    page.goto(f"{live_server}changes/STL/CC/timeline")
    page.get_by_label("Map box").select_option(value="mould")
    expect(page).to_have_url(re.compile(r"changes/STL/CC/timeline\?box=mould$"))
    rows = page.locator(".gantt__row")
    expect(rows).to_have_count(2)  # CC-31 (Mould powder) and CC-32 (Mould level control)


def test_renaming_a_link_type_changes_both_directions(live_server: str, page: Page) -> None:
    page.goto(live_server)
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.goto(f"{live_server}knowledge/STL/CC/fm-level")
    page.get_by_role("button", name="Kinds & links").click()
    settings = page.get_by_role("dialog", name="Kinds & link types")
    settings.get_by_role("button", name="Edit the link type leads to").click()
    form = settings.get_by_role("form", name="Edit the link type leads to")
    form.get_by_label("Forward").fill("results in")
    form.get_by_label("Backward").fill("results from")
    form.get_by_role("button", name="Save link type").click()
    settings.get_by_role("button", name="Done").click()
    panel = _panel(page)
    expect(panel.get_by_role("heading", name="Results in")).to_be_visible()
    expect(panel.get_by_role("heading", name="Results from")).to_be_visible()


def test_a_task_points_into_the_map(editors: None, live_server: str, page: Page) -> None:
    page.goto(live_server)
    log_in(page, "editor", PASSWORD)
    page.goto(f"{live_server}t/104")
    field = page.locator(".field", has=page.get_by_text("Knowledge map", exact=True))
    expect(field.locator(".box-link")).to_have_text(
        ["Continuous casting › Mould › Mould level control › Mould level fluctuation"]
    )
    field.get_by_role(
        "button",
        name="Unlink Continuous casting › Mould › Mould level control › Mould level fluctuation",
    ).click()
    expect(field.locator(".box-link")).to_have_count(0)
