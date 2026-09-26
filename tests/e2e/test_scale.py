"""A board with 5,000 extra tasks in a real browser (milestone M10).

Measured on a laptop: Priority ~1.3 s to show every row, search ~0.1 s, People ~1.2 s. The
limits are several times that, so they catch regressions, not slow machines.
"""

import time

from playwright.sync_api import Page, expect

from taskboard.db.session import Database
from tests.scale import add_tasks


def test_a_big_board_stays_usable(
    live_server: str, page: Page, sample_database: Database, console_errors: list[str]
) -> None:
    with sample_database.session(write=True) as s:
        add_tasks(s, 5000)
    rows = page.locator(".task-row")

    start = time.perf_counter()
    page.goto(f"{live_server}priority")
    expect(page.locator(".count-note")).to_contain_text("of 5011 tasks", timeout=15_000)
    shown = rows.count()
    assert shown > 3000
    assert time.perf_counter() - start < 5

    start = time.perf_counter()
    page.get_by_placeholder("Search title or description…").fill("roll grinding")
    expect(rows).not_to_have_count(shown)
    assert time.perf_counter() - start < 1.5

    start = time.perf_counter()
    page.get_by_role("link", name="People").click()
    expect(page.locator(".lane").first).to_be_visible(timeout=15_000)
    assert time.perf_counter() - start < 5
    assert console_errors == []
