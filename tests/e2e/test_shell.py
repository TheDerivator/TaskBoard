"""The app shell and the Tasks view in a real browser: filters, theme, sidebar, login, rank
numbers on request."""

import re

from playwright.sync_api import Browser, Locator, Page, expect
from sqlalchemy import update

from taskboard.db.models import User
from taskboard.db.session import Database
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in
from tests.helpers import revoke_anonymous_access


def rows(page: Page) -> Locator:
    return page.locator(".task-row")


def sidebar_login(page: Page) -> Locator:
    return page.locator(".sidebar").get_by_role("button", name="Log in")


def test_tasks_lists_every_task_in_order_hiding_archived(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(live_server)  # "/" redirects to /tasks
    expect(page).to_have_url(f"{live_server}tasks")
    expect(rows(page)).to_have_count(10)
    first = rows(page).first
    expect(rows(page).locator(".rank")).to_have_count(0)  # rank numbers only on request (D-103)
    expect(page.locator(".task-table__head")).not_to_contain_text("Rank")
    expect(first.locator(".task-title")).to_have_text(
        "Root-cause analysis of surface defects on line 2"
    )
    expect(first.locator(".task-key")).to_have_text("T-104")
    expect(first.locator(".project-chip")).to_contain_text("2.1")
    expect(page.locator(".count-note")).to_contain_text("Showing 10 of 11 tasks")
    expect(page).to_have_title("Tasks · Team Tasks")
    assert console_errors == []


def test_search_and_filters_never_change_ranks(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}tasks")
    page.get_by_placeholder("Search title or description…").fill("ROLL")
    expect(rows(page)).to_have_count(2)
    expect(rows(page).locator(".task-key")).to_have_text(["T-104", "T-098"])  # ranks 1 and 3
    page.get_by_role("button", name="Reset filters").click()
    expect(rows(page)).to_have_count(10)

    page.get_by_role("button", name="Archived").click()
    expect(rows(page)).to_have_count(11)
    page.get_by_role("button", name="Idea").click()
    expect(rows(page)).to_have_count(7)

    page.get_by_label("Department").select_option(label="R&D")
    expect(rows(page)).to_have_count(1)
    expect(rows(page).locator(".task-key")).to_have_text(["T-130"])  # rank 4
    expect(page.get_by_label("Section").locator("option")).to_have_text(["All", "Coatings"])
    assert console_errors == []


def test_the_old_address_leads_to_the_task_list(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")  # bookmarks from before the list was renamed (D-103)
    expect(page).to_have_url(f"{live_server}tasks")
    expect(page.get_by_role("heading", name="Tasks", level=1)).to_be_visible()
    expect(page.get_by_role("link", name=re.compile("^Tasks"))).to_have_attribute(
        "aria-current", "page"
    )


def test_rank_numbers_on_request(
    live_server: str, page: Page, browser: Browser, console_errors: list[str]
) -> None:
    """The profile's "Show rank numbers" shows them in every view, in every browser (D-103)."""
    page.goto(f"{live_server}tasks")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(rows(page)).to_have_count(10)
    expect(rows(page).locator(".rank")).to_have_count(0)

    page.goto(f"{live_server}profile")
    checkbox = page.get_by_role("checkbox", name="Show rank numbers")
    expect(checkbox).not_to_be_checked()
    expect(checkbox).to_have_accessible_description(re.compile("team-wide rank"))
    checkbox.check()
    expect(page.get_by_role("status")).to_contain_text("Rank numbers are shown.")
    expect(checkbox).to_be_checked()

    page.goto(f"{live_server}tasks")
    expect(rows(page).first.locator(".rank")).to_have_text("01")
    expect(page.locator(".task-table__head")).to_contain_text("Rank")
    page.goto(f"{live_server}people")
    expect(page.get_by_role("region", name="Anna Claes").locator(".card__rank")).to_have_text(
        ["#01", "#02", "#07", "#10"]
    )
    page.goto(f"{live_server}projects/ASQ")
    expect(page.locator(".outline-row__rank").first).to_have_text("#02")
    page.goto(f"{live_server}t/098")
    expect(page.locator(".task-page .rank-badge")).to_have_text("Rank 03 of 11")

    # Kept with the account, not the browser: signing in elsewhere shows them too.
    elsewhere = browser.new_context()
    other = elsewhere.new_page()
    other.goto(f"{live_server}tasks")
    log_in(other, "admin", TEST_ADMIN_PASSWORD)
    expect(rows(other).first.locator(".rank")).to_have_text("01")
    elsewhere.close()

    page.goto(f"{live_server}profile")
    page.get_by_role("checkbox", name="Show rank numbers").uncheck()
    expect(page.get_by_role("status")).to_contain_text("Rank numbers are hidden.")
    page.goto(f"{live_server}tasks")
    expect(rows(page)).to_have_count(10)
    expect(rows(page).locator(".rank")).to_have_count(0)
    assert console_errors == []


def test_theme_choice_survives_a_reload(live_server: str, page: Page) -> None:
    page.emulate_media(color_scheme="light")
    page.goto(f"{live_server}tasks")
    html = page.locator("html")
    expect(html).to_have_attribute("data-theme", "light")
    page.get_by_test_id("theme-toggle").click()
    expect(html).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(html).to_have_attribute("data-theme", "dark")


def test_the_system_theme_is_the_default(live_server: str, page: Page) -> None:
    page.emulate_media(color_scheme="dark")
    page.goto(f"{live_server}tasks")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def test_sidebar_collapse_survives_a_reload(live_server: str, page: Page) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{live_server}tasks")
    page.get_by_role("button", name="Collapse sidebar").click()
    expect(page.locator(".app")).to_have_class("app is-collapsed")
    expect(page.locator(".sidebar__name")).to_be_hidden()
    page.reload()
    expect(page.locator(".app")).to_have_class("app is-collapsed")
    page.get_by_role("button", name="Expand sidebar").click()
    expect(page.locator(".sidebar__name")).to_be_visible()


def test_nothing_is_loaded_from_other_origins(live_server: str, page: Page) -> None:
    requested: list[str] = []
    page.on("request", lambda request: requested.append(request.url))
    page.goto(f"{live_server}tasks")
    expect(rows(page)).to_have_count(10)
    page.wait_for_load_state("networkidle")
    assert requested, "no requests recorded"
    assert [url for url in requested if not url.startswith(live_server)] == []
    assert any(url.endswith(".woff2") for url in requested)  # the self-hosted fonts are in use


def test_login_and_logout(live_server: str, page: Page, console_errors: list[str]) -> None:
    page.goto(f"{live_server}tasks")
    sidebar_login(page).click()
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_label("Username").fill("admin")
    dialog.get_by_label("Password").fill("wrong password")
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog.get_by_role("alert")).to_have_text("unknown username or wrong password")
    dialog.get_by_label("Password").fill(TEST_ADMIN_PASSWORD)
    dialog.get_by_role("button", name="Log in").click()
    expect(dialog).to_be_hidden()
    expect(page.locator(".sidebar__user-name")).to_have_text("Administrator")
    expect(page.get_by_role("button", name="New task")).to_be_visible()

    page.get_by_role("button", name="Log out").click()
    expect(sidebar_login(page)).to_be_visible()
    assert console_errors == []


def test_a_login_only_board_asks_visitors_to_log_in(
    live_server: str, page: Page, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as session:
        revoke_anonymous_access(session)
    page.goto(f"{live_server}tasks")
    expect(page.get_by_role("heading", name="Log in to see the board")).to_be_visible()
    form = page.locator("#content")
    form.get_by_label("Username").fill("admin")
    form.get_by_label("Password").fill(TEST_ADMIN_PASSWORD)
    form.get_by_role("button", name="Log in").click()
    expect(rows(page)).to_have_count(10)


def test_a_required_password_change_cannot_be_skipped(
    live_server: str, page: Page, sample_database: Database
) -> None:
    with sample_database.session(write=True) as session:
        session.execute(
            update(User).where(User.username == "admin").values(must_change_password=True)
        )
    page.goto(f"{live_server}tasks")
    sidebar_login(page).click()
    login = page.get_by_role("dialog", name="Log in")
    login.get_by_label("Username").fill("admin")
    login.get_by_label("Password").fill(TEST_ADMIN_PASSWORD)
    login.get_by_role("button", name="Log in").click()

    dialog = page.get_by_role("dialog", name="Choose a new password")
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).to_be_visible()
    dialog.get_by_label("Current password").fill(TEST_ADMIN_PASSWORD)
    dialog.get_by_label("New password (at least 10 characters)").fill("a brand new password")
    dialog.get_by_label("New password again").fill("a brand new password")
    dialog.get_by_role("button", name="Save password").click()
    expect(dialog).to_be_hidden()
    expect(rows(page)).to_have_count(10)


def test_unknown_addresses_show_not_found(live_server: str, page: Page) -> None:
    response = page.goto(f"{live_server}no/such/page")
    assert response is not None and response.status == 404
    expect(page.get_by_role("heading", name="Page not found")).to_be_visible()


def test_navigation_on_a_phone(live_server: str, page: Page) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{live_server}tasks")
    expect(page.get_by_role("link", name="People")).to_be_hidden()
    page.get_by_role("button", name="Open navigation").click()
    page.get_by_role("link", name="People").click()
    expect(page).to_have_url(f"{live_server}people")
    expect(page.get_by_role("link", name=re.compile("^Tasks"))).to_be_hidden()


def test_every_view_runs_under_the_content_security_policy(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    """The browser enforces the strict CSP; any blocked script, style, font or image fails this."""
    page.add_init_script(
        "window.addEventListener('securitypolicyviolation', (e) =>"
        " console.error(`CSP blocked ${e.blockedURI} (${e.effectiveDirective})`))"
    )
    page.goto(f"{live_server}tasks")
    expect(rows(page)).to_have_count(10)
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    tour = {
        "people": page.locator(".lane"),
        "projects": page.locator(".project-tree"),
        "t/104/conversation": page.locator(".post .md img"),  # an uploaded image
        "admin/users": page.get_by_role("heading", name="Accounts"),
        "admin/audit": page.get_by_role("heading", name="Audit log"),
    }
    for path, landmark in tour.items():
        page.goto(f"{live_server}{path}")
        expect(landmark.first).to_be_visible()
    assert console_errors == []
