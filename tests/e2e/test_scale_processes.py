"""2,000 process changes and a 2,000-box map in a real browser (milestone M20).

Measured on a laptop: change list ~1.2 s, timeline ~1.1 s, map plus "Expand all" ~1.4 s, FMEA
~1.0 s, control plan ~0.4 s, search ~0.4 s (each step prints its time with -s). The limits are
several times that, so they catch regressions, not slow machines.
"""

import time
from collections.abc import Callable

from playwright.sync_api import Page, expect

from taskboard.db.session import Database
from tests.scale import add_changes, add_map


def _within(seconds: float, what: str, step: Callable[[], None]) -> None:
    start = time.perf_counter()
    step()
    elapsed = time.perf_counter() - start
    print(f"{what}: {elapsed:.2f}s")
    assert elapsed < seconds, f"{what} took {elapsed:.2f}s (limit {seconds}s)"


def test_big_processes_stay_usable(
    live_server: str, page: Page, sample_database: Database, console_errors: list[str]
) -> None:
    with sample_database.session(write=True) as s:
        add_changes(s, "LM", 2000)
        add_map(s, "CC", 2000)
    long = 20_000

    def changes() -> None:
        page.goto(f"{live_server}changes/STL/LM")
        expect(page.locator(".change-row")).to_have_count(2006, timeout=long)  # 6 in the sample

    def timeline() -> None:
        page.goto(f"{live_server}changes/STL/LM/timeline")
        expect(page.locator(".gantt__row").first).to_be_visible(timeout=long)

    def whole_map() -> None:
        page.goto(f"{live_server}knowledge/STL/CC")
        expect(page.locator('.map-box[data-box="gen-zone-0"]')).to_be_visible(timeout=long)
        page.get_by_role("button", name="Expand all").click()
        expect(page.locator('.map-box[data-box="gen-fm-1"]')).to_be_visible(timeout=long)

    def fmea() -> None:
        page.goto(f"{live_server}fmea/STL/CC")
        bar = page.get_by_role("group", name="Released versions")
        expect(bar).to_contain_text("since v3", timeout=long)
        expect(page.locator('.map-box[data-box="gen-fm-1"]')).to_be_visible(timeout=long)

    def control_plan() -> None:
        page.goto(f"{live_server}cpl/STL")
        diagram = page.get_by_role("region", name="How it arises")
        expect(diagram.locator(".cpl-node--cause").first).to_be_visible(timeout=long)

    def search() -> None:
        page.keyboard.press("Control+k")
        dialog = page.get_by_role("dialog", name="Search everything")
        dialog.get_by_role("combobox").fill("generated cooling")
        expect(dialog.get_by_role("option").first).to_be_visible(timeout=long)

    _within(6, "change list", changes)
    _within(6, "timeline", timeline)
    _within(10, "map, then expand all", whole_map)
    _within(8, "FMEA", fmea)
    _within(5, "control plan", control_plan)
    _within(3, "search", search)
    assert console_errors == []
