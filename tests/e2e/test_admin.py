"""Administration in a real browser (milestone M8), with a second browser for "the other person"."""

import re
from collections.abc import Iterator

import pytest
from playwright.sync_api import Browser, Page, expect

from taskboard.config import Settings
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in
from tests.helpers import fake_backups


@pytest.fixture
def other(browser: Browser) -> Iterator[Page]:
    """A second, separate browser session (its own cookies)."""
    context = browser.new_context()
    page = context.new_page()
    page.set_default_timeout(10_000)
    yield page
    context.close()


def open_admin(page: Page, live_server: str) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("link", name="Administration").click()
    expect(page.get_by_role("heading", name="Accounts")).to_be_visible()


def create_account(page: Page, username: str, display_name: str) -> str:
    """Create a local account with a generated password through the UI; returns the password."""
    page.get_by_role("button", name="New account").click()
    dialog = page.get_by_role("dialog", name="New account")
    dialog.get_by_label("Username").fill(username)
    dialog.get_by_label("Display name").fill(display_name)
    dialog.get_by_label("Initial role (optional)").select_option(label="Editor")
    dialog.get_by_label("Where").select_option(label="STL (whole department)")
    dialog.get_by_role("button", name="Create account").click()
    password = dialog.locator(".secret-box code").inner_text()
    dialog.get_by_role("button", name="Done").click()
    return password


def test_create_an_account_and_its_first_login(
    live_server: str, page: Page, other: Page, console_errors: list[str]
) -> None:
    open_admin(page, live_server)
    password = create_account(page, "nina.vos", "Nina Vos")
    assert len(password) >= 16
    row = page.locator(".data-table tbody tr", has_text="Nina Vos")
    expect(row).to_contain_text("Editor · STL")

    other.goto(f"{live_server}priority")
    log_in(other, "nina.vos", password)
    dialog = other.get_by_role("dialog", name="Choose a new password")
    dialog.get_by_label("Current password").fill(password)
    dialog.get_by_label("New password (at least 10 characters)").fill("ninas own password")
    dialog.get_by_label("New password again").fill("ninas own password")
    dialog.get_by_role("button", name="Save password").click()
    expect(other.get_by_role("button", name="New task")).to_be_visible()  # Editor rights apply
    assert console_errors == []


def test_suspending_an_account_logs_it_out(live_server: str, page: Page, other: Page) -> None:
    open_admin(page, live_server)
    password = create_account(page, "sam", "Sam")
    other.goto(f"{live_server}priority")
    log_in(other, "sam", password)
    expect(other.get_by_role("dialog", name="Choose a new password")).to_be_visible()

    page.locator(".data-table tbody tr", has_text="Sam").click()
    page.get_by_role("dialog", name="Sam").get_by_role("button", name="Suspend").click()
    expect(page.locator(".data-table tbody tr", has_text="Sam")).to_contain_text("Suspended")

    other.reload()
    expect(other.locator(".sidebar").get_by_role("button", name="Log in")).to_be_visible()


def test_revoking_anonymous_access_requires_login(
    live_server: str, page: Page, other: Page
) -> None:
    other.goto(f"{live_server}priority")
    expect(other.locator(".task-row").first).to_be_visible()

    open_admin(page, live_server)
    page.locator(".data-table tbody tr", has_text="Anonymous visitors").click()
    dialog = page.get_by_role("dialog", name="Anonymous visitors")
    dialog.get_by_role("button", name="Remove Viewer (Everywhere)").click()
    expect(dialog.get_by_text("No roles.")).to_be_visible()

    other.reload()
    expect(other.get_by_role("heading", name="Log in to see the board")).to_be_visible()


def test_the_last_administrator_cannot_remove_their_own_rights(
    live_server: str, page: Page
) -> None:
    open_admin(page, live_server)
    page.locator(".data-table tbody tr", has_text="@admin").click()
    dialog = page.get_by_role("dialog", name="Administrator")
    expect(dialog.get_by_role("button", name="Suspend")).to_have_count(0)  # not for yourself
    dialog.get_by_role("button", name="Remove Administrator (Everywhere)").click()
    expect(dialog.get_by_role("alert")).to_contain_text("keep at least one active administrator")


def test_non_administrators_see_no_administration(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}admin/users")
    expect(page.get_by_role("link", name="Administration")).to_have_count(0)
    expect(page.get_by_text("You have no administration rights.")).to_be_visible()


def test_custom_role_organization_and_people(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    open_admin(page, live_server)

    page.get_by_role("link", name="Roles").click()
    form = page.get_by_role("form", name="New role")
    form.get_by_label("Name").fill("Commenter")
    form.get_by_label(re.compile("^Key")).fill("commenter")
    form.locator(".check", has_text="task.comment").locator("input").check()
    form.get_by_role("button", name="Create role").click()
    expect(page.get_by_role("region", name="Role Commenter")).to_be_visible()

    page.get_by_role("link", name="Organization").click()
    page.get_by_label("New section in STL").fill("Logistics")
    page.get_by_role("region", name="Department STL").get_by_role(
        "button", name="Add section"
    ).click()
    expect(page.get_by_role("textbox", name="Section Logistics", exact=True)).to_have_value(
        "Logistics"
    )

    page.get_by_role("link", name="People", exact=True).last.click()
    page.get_by_role("button", name="New person").click()
    dialog = page.get_by_role("dialog", name="New person")
    dialog.get_by_label("Name").fill("Greet Vos")
    dialog.get_by_label("Code (initials)").fill("gv")
    dialog.get_by_label("Section").select_option(label="STL · Logistics")
    dialog.get_by_role("button", name="Save").click()
    expect(page.locator(".data-table tbody tr", has_text="Greet Vos")).to_contain_text(
        "STL · Logistics"
    )

    page.get_by_role("link", name="Audit log").click()
    expect(page.locator(".data-table tbody tr").first).to_contain_text("person.created")
    assert console_errors == []


def test_sso_group_mappings(live_server: str, page: Page, console_errors: list[str]) -> None:
    open_admin(page, live_server)
    page.locator(".admin-tabs").get_by_role("link", name="SSO groups").click()
    expect(page.get_by_text("No SSO provider that reports groups is configured")).to_be_visible()
    form = page.get_by_role("form", name="New group mapping")
    form.get_by_label("Provider", exact=True).fill("proxy")
    form.get_by_label("Group (as the provider sends it").fill("STL-Maintenance")
    form.get_by_label("Role").select_option(label="Editor")
    form.get_by_label("Where").select_option(label="STL · Maintenance")
    form.get_by_role("button", name="Add mapping").click()
    row = page.locator(".data-table tbody tr", has_text="STL-Maintenance")
    expect(row).to_contain_text("Editor")
    expect(row).to_contain_text("STL · Maintenance")
    expect(form.get_by_label("Group (as the provider sends it")).to_have_value("")
    row.get_by_role("button", name="Remove mapping for STL-Maintenance").click()
    expect(page.get_by_text("No group mappings yet.")).to_be_visible()
    assert console_errors == []


def test_backups_and_how_many_to_keep(
    live_server: str, settings: Settings, page: Page, console_errors: list[str]
) -> None:
    folder = settings.resolved_backup_dir
    fake_backups(folder, "2025-03-06", "2025-03-05", "2025-03-04", "2025-03-03", "2025-02-10")
    open_admin(page, live_server)
    page.locator(".admin-tabs").get_by_role("link", name="Backups").click()
    expect(page.locator(".notice--danger")).to_contain_text("more than two days ago")
    expect(page.locator(".backup-folder code")).to_have_text(str(folder))
    rows = page.locator(".data-table tbody tr")
    expect(rows).to_have_count(5)
    expect(rows.nth(0)).to_contain_text("6 Mar 2025")
    expect(rows.nth(2)).to_contain_text("Deleted at the next backup")
    expect(rows.nth(3)).to_contain_text("First of the week")

    form = page.get_by_role("form", name="How many to keep")
    expect(form.get_by_role("button", name="Save")).to_be_disabled()  # nothing changed yet
    form.get_by_label("Newest backups").fill("3")
    form.get_by_role("button", name="Save").click()
    expect(page.get_by_text("Saved. The next backup deletes")).to_be_visible()
    expect(rows.nth(2)).to_contain_text("Newest")
    page.reload()
    expect(form.get_by_label("Newest backups")).to_have_value("3")
    assert console_errors == []
