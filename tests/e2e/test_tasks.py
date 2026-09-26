"""Priority interactions and the task drawer in a real browser (milestone M5)."""

import re

from fastapi.testclient import TestClient
from playwright.sync_api import Page, expect
from sqlalchemy import select

from taskboard.config import Settings
from taskboard.db.models import Task
from taskboard.db.session import Database
from taskboard.web import create_app
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.e2e.conftest import log_in
from tests.helpers import login, revoke_anonymous_access


def keys(page: Page) -> list[str]:
    return page.locator(".task-row .task-key").all_inner_texts()


def drag(page: Page, source_index: int, target_index: int) -> None:
    """Press on a row's department cell, move in steps (past the threshold), drop on another row."""
    source = page.locator(".task-row").nth(source_index).locator(".task-org").bounding_box()
    target = page.locator(".task-row").nth(target_index).locator(".task-org").bounding_box()
    assert source and target
    page.mouse.move(source["x"] + 5, source["y"] + 5)
    page.mouse.down()
    page.mouse.move(source["x"] + 5, source["y"] + 15, steps=3)
    page.mouse.move(target["x"] + 5, target["y"] + 5, steps=10)
    page.mouse.up()


def test_dragging_a_row_changes_the_team_ranking(
    live_server: str, page: Page, sample_database: Database, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.locator(".task-list--sortable")).to_be_visible()
    drag(page, 4, 1)  # T-089 (rank 5) dropped on T-117 (rank 2): upwards → before it
    expect(page.locator(".task-row .task-key").nth(1)).to_have_text("T-089")
    page.reload()
    expect(page.locator(".task-row .task-key").nth(1)).to_have_text("T-089")
    assert keys(page)[:4] == ["T-104", "T-089", "T-117", "T-098"]
    with sample_database.session() as s:
        assert s.scalars(select(Task.rank).where(Task.key == "089")).one() == 2
    assert console_errors == []


def test_reordering_with_the_keyboard(
    live_server: str, page: Page, sample_database: Database, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    grip = page.get_by_role("button", name="Move T-089, rank 5")
    grip.focus()
    expect(grip).to_have_accessible_description(re.compile("Arrow Up and Arrow Down"))
    page.keyboard.press("ArrowUp")
    moved = page.get_by_role("button", name="Move T-089, rank 4")
    expect(moved).to_be_focused()  # focus follows the task
    page.keyboard.press("ArrowUp")
    page.keyboard.press("ArrowUp")  # quick presses are saved in order
    expect(page.get_by_role("button", name="Move T-089, rank 2")).to_be_focused()
    page.keyboard.press("Home")
    expect(page.get_by_role("button", name="Move T-089, rank 1")).to_be_focused()
    page.keyboard.press("ArrowUp")  # already at the top: nothing happens
    page.keyboard.press("End")
    expect(page.get_by_role("button", name=re.compile(r"Move T-089, rank 1[01]"))).to_be_focused()
    page.keyboard.press("Home")
    expect(page.get_by_role("button", name="Move T-089, rank 1")).to_be_focused()
    page.wait_for_load_state("networkidle")
    page.reload()
    expect(page.locator(".task-row .task-key").first).to_have_text("T-089")
    assert keys(page)[:3] == ["T-089", "T-104", "T-117"]
    with sample_database.session() as s:
        assert s.scalars(select(Task.rank).where(Task.key == "089")).one() == 1
    assert console_errors == []


def test_visitors_cannot_drag(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    expect(page.locator(".task-row").first).to_be_visible()
    expect(page.locator(".task-list--sortable")).to_have_count(0)
    drag(page, 4, 1)
    assert keys(page)[:2] == ["T-104", "T-117"]


def test_edit_a_task_in_the_drawer(live_server: str, page: Page, console_errors: list[str]) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name="Coating adhesion trial, batch 3").click()
    expect(page).to_have_url(f"{live_server}t/130")
    drawer = page.get_by_role("dialog", name="Task 130")
    expect(drawer.locator(".rank-badge")).to_have_text("Rank 04 of 11")
    save = drawer.get_by_role("button", name="Save task")
    expect(save).to_be_disabled()  # nothing changed yet

    drawer.get_by_label("Title").fill("Coating adhesion trial, batch 4")
    drawer.get_by_role("button", name="Done").click()
    drawer.get_by_role("button", name="Remove Filip Maes").click()
    drawer.get_by_role("button", name="+ Add person").click()
    page.get_by_role("listbox", name="Add a person").get_by_role(
        "option", name="Eva Janssens"
    ).click()
    save.click()

    expect(drawer).to_be_hidden()
    expect(page).to_have_url(f"{live_server}priority")
    row = page.locator(".task-row", has_text="Coating adhesion trial, batch 4")
    expect(row.locator(".pill")).to_have_text("Done")
    expect(row.locator(".avatar-stack .avatar")).to_have_text(["EJ"])
    assert console_errors == []


def test_choosing_a_new_lead(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}t/126")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="Lead · exactly one Filip Maes").click()
    picker = page.get_by_role("searchbox", name="Choose the lead")
    picker.fill("dries")
    picker.press("Enter")
    expect(page.locator(".person-button__name")).to_have_text("Dries Wouters")
    page.get_by_role("button", name="Save task").click()
    expect(page.get_by_role("status")).to_contain_text("T-126 saved.")


def test_a_concurrent_edit_is_detected(live_server: str, page: Page, settings: Settings) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name="Guard rail check at the coiler").click()
    drawer = page.get_by_role("dialog", name="Task 110")
    drawer.get_by_label("Title").fill("My version")

    # Someone else saves first (through the API, with their own session).
    other = start_client(create_app(settings))
    client: TestClient = next(other)
    login(client, "admin", TEST_ADMIN_PASSWORD)
    version = client.get("/api/tasks/110").json()["version"]
    assert (
        client.patch(
            "/api/tasks/110", json={"version": version, "title": "Their version"}
        ).status_code
        == 200
    )
    other.close()

    drawer.get_by_role("button", name="Save task").click()
    expect(drawer.get_by_role("alert")).to_contain_text("Someone else changed this task")
    drawer.get_by_role("button", name="Reload").click()
    expect(drawer.get_by_label("Title")).to_have_value("Their version")


def test_add_the_task_to_another_project(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}t/104")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="+ Add to another project").click()
    dialog = page.get_by_role("dialog", name="Add to another project")
    expect(dialog.get_by_role("radio", name="Action plan surface quality")).to_be_disabled()
    expect(dialog).to_contain_text("Already in 2.1 Root cause. Use Move to change it.")
    dialog.get_by_role("radio", name="Projects 2026").check()
    dialog.get_by_role("radio", name="1.1 Inspection").check()
    expect(dialog.locator(".dialog__summary")).to_have_text("Projects 2026 › 1.1 Inspection")
    dialog.get_by_role("button", name="Add").click()
    expect(dialog).to_be_hidden()
    expect(page.locator(".placement", has_text="Projects 2026")).to_contain_text(
        "1 Investments › 1.1 Inspection"
    )

    page.locator(".placement", has_text="Projects 2026").get_by_role(
        "button", name="Move", exact=True
    ).click()
    move = page.get_by_role("dialog", name="Move within project")
    move.get_by_role("radio", name="Top level (no section)").check()
    move.get_by_role("button", name="Move", exact=True).click()
    expect(page.locator(".placement", has_text="Projects 2026")).to_contain_text("Top level")
    page.get_by_role("button", name="Remove from Projects 2026").click()
    expect(page.locator(".placement")).to_have_count(1)


def test_visitors_see_a_read_only_task(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    page.get_by_role("link", name="Root-cause analysis of surface defects on line 2").click()
    drawer = page.get_by_role("dialog", name="Task 104")
    expect(
        drawer.get_by_role(
            "heading", name="Root-cause analysis of surface defects on line 2", exact=True
        )
    ).to_be_visible()
    expect(drawer.get_by_role("textbox")).to_have_count(0)
    expect(drawer.get_by_role("button", name="Save task")).to_have_count(0)
    expect(drawer.get_by_role("button", name="+ Add to another project")).to_have_count(0)
    page.keyboard.press("Escape")
    expect(drawer).to_be_hidden()
    expect(page).to_have_url(f"{live_server}priority")


def test_the_permalink_opens_the_task_page_and_can_be_copied(live_server: str, page: Page) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    page.goto(f"{live_server}t/t-098")
    expect(page.locator(".task-page .task-panel__key")).to_have_text("T-098")
    expect(page.locator(".task-page .rank-badge")).to_have_text("Rank 03 of 11")
    page.get_by_role("button", name="Copy link to this task").click()
    expect(page.get_by_role("status")).to_contain_text("Link copied.")
    assert page.evaluate("navigator.clipboard.readText()") == f"{live_server}t/098"


def test_login_returns_to_the_requested_task(
    live_server: str, page: Page, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as session:
        revoke_anonymous_access(session)
    page.goto(f"{live_server}t/104")
    form = page.locator("#content")
    form.get_by_label("Username").fill("admin")
    form.get_by_label("Password").fill(TEST_ADMIN_PASSWORD)
    form.get_by_role("button", name="Log in").click()
    expect(page).to_have_url(f"{live_server}t/104")
    expect(page.locator(".task-panel__key")).to_have_text("T-104")


def test_unknown_tasks_say_so(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}t/ZZZZZZ")
    expect(page.get_by_role("alert")).to_have_text(
        "This task doesn't exist, or you don't have access to it."
    )


def test_create_a_new_task(live_server: str, page: Page, console_errors: list[str]) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="New task").click()
    drawer = page.get_by_role("dialog", name="New task")
    create = drawer.get_by_role("button", name="Create task")
    expect(create).to_be_disabled()
    drawer.get_by_label("Title").fill("Replace the coiler light curtain")
    drawer.get_by_label("Department").select_option(label="STL")
    drawer.get_by_label("Section").select_option(label="Maintenance")
    drawer.get_by_role("button", name="+ Add to another project").click()
    dialog = page.get_by_role("dialog", name="Add to another project")
    dialog.get_by_role("radio", name="Safety 2026").check()
    dialog.get_by_role("radio", name="1.1 Coiler").check()
    dialog.get_by_role("button", name="Add").click()
    create.click()

    task_drawer = page.locator(".drawer .task-panel__key")
    expect(task_drawer).to_have_text(re.compile(r"^T-[0-9A-Z]{6}$"))
    expect(page.locator(".drawer .rank-badge")).to_have_text("Rank 12 of 12")
    page.keyboard.press("Escape")
    last = page.locator(".task-row").last
    expect(last.locator(".task-title")).to_have_text("Replace the coiler light curtain")
    expect(last.locator(".rank")).to_have_text("12")
    expect(last.locator(".project-chip")).to_contain_text("Safety 2026")
    assert console_errors == []


def test_unsaved_changes_are_not_lost_by_accident(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name="Update SPC dashboards for thickness").click()
    drawer = page.get_by_role("dialog", name="Task 126")
    drawer.get_by_label("Title").fill("Half-typed title")

    page.once("dialog", lambda d: d.dismiss())  # "Discard your unsaved changes?" → no
    page.keyboard.press("Escape")
    expect(drawer).to_be_visible()
    expect(drawer.get_by_label("Title")).to_have_value("Half-typed title")

    page.once("dialog", lambda d: d.accept())  # → yes, discard
    drawer.get_by_role("button", name="Cancel").click()
    expect(drawer).to_be_hidden()
