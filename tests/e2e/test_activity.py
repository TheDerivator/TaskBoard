"""Recent activity in a real browser (milestone M25): tasks by their newest post, per project or
section, the task's conversation over the list, and "Show older"."""

import re
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from playwright.sync_api import Locator, Page, expect
from sqlalchemy import select

from taskboard.db.models import Post, Task, User
from taskboard.db.session import Database
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in
from tests.scale import add_tasks

TITLES = {
    "121": "Budget proposal for inline camera system",
    "130": "Coating adhesion trial, batch 3",
    "089": "Operator training: defect classification",
    "098": "Tonnage-based work-roll regrinding",
    "133": "Roadmap workshop for next year",
    "104": "Root-cause analysis of surface defects on line 2",
    "110": "Guard rail check at the coiler",
    "075": "Audit of coil handling damage",
}
BY_ACTIVITY = ["121", "130", "089", "098", "133", "104", "110", "075"]  # newest post first


@pytest.fixture
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    """The sample's times are Belgian: in that time zone the page shows them as written."""
    return {**browser_context_args, "timezone_id": "Europe/Brussels"}


def items(page: Page) -> Locator:
    return page.locator(".activity-item")


def picker(page: Page, label: str) -> Locator:
    """A select by its label (its name also holds the option chosen: "Project All projects")."""
    return page.get_by_role("combobox", name=re.compile(f"^{label}"))


def expect_tasks(page: Page, keys: list[str]) -> None:
    expect(items(page).locator(".task-title")).to_have_text([TITLES[k] for k in keys])


def test_tasks_by_their_newest_post(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}tasks")
    page.locator(".sidebar").get_by_role("link", name="Recent activity").click()
    expect(page).to_have_url(f"{live_server}activity")
    expect(page.locator("#content h1")).to_have_text("Recent activity")
    expect_tasks(page, BY_ACTIVITY)  # tasks without posts are not listed

    newest = items(page).first
    expect(newest.locator(".task-key")).to_have_text("T-121")
    expect(newest.locator(".activity-item__author")).to_have_text("Bram Peeters")
    expect(newest.locator(".activity-item__excerpt")).to_have_text(
        re.compile(r"^The third quote is in\. Comparison table: camera-quotes\.xlsx\.")
    )
    expect(newest).to_contain_text("2 posts")
    expect(newest.locator(".update-badge")).to_have_count(0)
    expect(items(page).nth(1).locator(".update-badge")).to_have_text("Status update")
    expect(newest.locator("time")).to_have_text("11:40")  # under its day's heading
    expect(page.locator(".activity-day").first).to_have_text(re.compile(r"^2 Oct( 2026)?$"))
    expect(page.locator(".count-note")).to_contain_text("Showing 8 tasks")
    expect(page.get_by_role("button", name="Show older")).to_have_count(0)
    assert console_errors == []


def test_a_new_post_moves_its_task_to_the_top(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}activity")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name=TITLES["104"]).click()
    expect(page).to_have_url(f"{live_server}t/104/conversation")
    drawer = page.get_by_role("dialog", name="Task 104")  # over the list, on its conversation
    expect(drawer.locator(".post")).to_have_count(4)
    composer = drawer.get_by_role("textbox", name="Write a comment")
    composer.fill("Overlay done: the cluster matches the **roll change**.")
    composer.press("Control+Enter")
    expect(drawer.locator(".post")).to_have_count(5)
    drawer.get_by_role("button", name="Close").click()

    expect(page).to_have_url(f"{live_server}activity")
    expect_tasks(page, ["104", *[k for k in BY_ACTIVITY if k != "104"]])
    newest = items(page).first
    expect(newest.locator(".activity-item__excerpt")).to_have_text(
        "Overlay done: the cluster matches the roll change."
    )
    expect(newest.locator("time")).to_have_text("just now")
    expect(newest).to_contain_text("5 posts")
    expect(page.locator(".activity-day").first).to_have_text("Today")
    assert console_errors == []


def test_a_project_and_one_of_its_sections(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}projects/ASQ")
    page.locator(".project-actions").get_by_role("link", name="Recent activity").click()
    expect(page).to_have_url(f"{live_server}activity/ASQ")
    expect_tasks(page, ["121", "089", "098", "104", "075"])

    picker(page, "Section").select_option(label="2 Line 2 defects")
    expect(page).to_have_url(re.compile(r"activity/ASQ\?node=\d+$"))
    expect_tasks(page, ["098", "104", "075"])  # the section and those below it
    page.go_back()
    expect_tasks(page, ["121", "089", "098", "104", "075"])

    picker(page, "Project").select_option(label="Safety 2026")
    expect(page).to_have_url(f"{live_server}activity/SAF")
    expect_tasks(page, ["110"])
    picker(page, "Project").select_option(label="All projects")
    expect(page).to_have_url(f"{live_server}activity")
    expect_tasks(page, BY_ACTIVITY)

    # A section of the Projects view leads to the same section here.
    page.goto(f"{live_server}projects/ASQ")
    page.locator(".project-tree").get_by_role("link", name=re.compile("Line 2 defects")).click()
    page.locator(".project-actions").get_by_role("link", name="Recent activity").click()
    expect(picker(page, "Section")).to_have_value(re.compile(r"^\d+$"))
    expect_tasks(page, ["098", "104", "075"])

    page.goto(f"{live_server}activity/NOPE")
    expect(page.get_by_role("alert")).to_have_text("This project doesn't exist.")
    assert console_errors == []


def test_show_older(
    live_server: str, page: Page, sample_database: Database, console_errors: list[str]
) -> None:
    with sample_database.session(write=True) as s:
        add_tasks(s, 40)
        admin = s.scalars(select(User.id).where(User.username == "admin")).one()
        generated = s.scalars(select(Task.id).where(Task.title.startswith("Generated"))).all()
        long_ago = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
        for minutes, task_id in enumerate(generated):
            s.add(
                Post(
                    task_id=task_id,
                    author_user_id=admin,
                    body_md="An older comment.",
                    created_at=long_ago - timedelta(minutes=minutes),
                )
            )
    page.goto(f"{live_server}activity")
    expect(items(page)).to_have_count(30)
    expect(page.locator(".count-note")).to_contain_text("Showing 30 tasks")
    page.get_by_role("button", name="Show older").click()
    expect(items(page)).to_have_count(48)
    expect(page.locator(".count-note")).to_contain_text("Showing 48 tasks")
    expect(page.get_by_role("button", name="Show older")).to_have_count(0)
    keys = items(page).evaluate_all("rows => rows.map(row => row.dataset.key)")
    assert len(set(keys)) == 48
    assert console_errors == []
