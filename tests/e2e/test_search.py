"""Search everything and stable links in a browser (milestone M19)."""

import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect


def _dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Search everything")


def _search(page: Page, query: str) -> Locator:
    dialog = _dialog(page)
    dialog.get_by_role("combobox").fill(query)
    expect(dialog.get_by_role("option").first).to_be_visible()
    return dialog


def test_ctrl_k_finds_mould_powder_and_enter_opens_the_box(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    expect(page.locator(".task-row").first).to_be_visible()
    page.keyboard.press("Control+k")
    dialog = _search(page, "mould powder")
    results = dialog.get_by_role("listbox", name="Results")
    for group in ("Knowledge", "Process changes", "Tasks", "Defects"):
        expect(results.get_by_role("group", name=group)).to_be_visible()
    filters = dialog.get_by_role("group", name="Filter results")
    expect(filters.get_by_role("button", name=re.compile(r"^All · \d+$"))).to_have_attribute(
        "aria-pressed", "true"
    )
    first = dialog.get_by_role("option").first
    expect(first).to_have_attribute("aria-selected", "true")
    expect(first).to_contain_text("/knowledge/STL/CC/m-powder")
    dialog.get_by_role("combobox").press("Enter")
    expect(_dialog(page)).to_have_count(0)
    expect(page).to_have_url(f"{live_server}knowledge/STL/CC/m-powder")
    panel = page.get_by_role("complementary", name="Selected box")
    expect(panel.get_by_role("heading", name="Mould powder")).to_be_visible()
    assert console_errors == []


def test_filters_and_the_arrow_keys(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    page.locator(".sidebar").get_by_role("button", name=re.compile("Search everything")).click()
    dialog = _search(page, "mould powder")
    dialog.get_by_role("button", name=re.compile(r"^Process changes · 1$")).click()
    options = dialog.get_by_role("option")
    expect(options).to_have_count(1)
    expect(options.first).to_contain_text("CC-31")
    expect(options.first).to_contain_text("in effect since 18 May")
    dialog.get_by_role("button", name=re.compile(r"^All · ")).click()
    combobox = dialog.get_by_role("combobox")
    combobox.press("ArrowDown")
    expect(options.nth(1)).to_have_attribute("aria-selected", "true")
    combobox.press("End")  # only with Ctrl: End stays in the text
    combobox.press("Control+End")
    expect(options.last).to_have_attribute("aria-selected", "true")
    expect(options.last).to_contain_text("/cpl/STL/")
    combobox.press("Enter")
    expect(page).to_have_url(re.compile(r"cpl/STL/d-"))


def test_ctrl_enter_opens_a_new_tab(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    page.keyboard.press("Control+k")
    dialog = _search(page, "LM-07")
    with page.context.expect_page() as opened:
        dialog.get_by_role("combobox").press("Control+Enter")
    expect(opened.value).to_have_url(re.compile(r"changes/STL/LM/LM-07$"))
    expect(_dialog(page)).to_be_visible()  # the search stays open here


# Every link of PLAN2's links table, as pasted into a fresh browser: where it lands, what shows.
LINKS = [
    ("changes/STL/LM", r"changes/STL/LM$", "Argon stirring rate during trim"),
    ("changes/STL/LM/timeline", r"changes/STL/LM/timeline$", "Argon stirring rate"),
    ("changes/STL/LM/LM-07", r"changes/STL/LM/LM-07$", "Argon stirring rate during trim"),
    ("changes/stl/cc/lm-07", r"changes/STL/LM/LM-07$", "Argon stirring rate during trim"),
    ("changes/STL/LM/LM-07/conversation", r"LM-07/conversation$", "Periods only"),
    ("knowledge/STL/CC", r"knowledge/STL/CC$", "Continuous casting"),
    ("knowledge/STL/CC/fm-level", r"knowledge/STL/CC/fm-level$", "Mould level fluctuation"),
    ("knowledge/STL/LM/fm-level", r"knowledge/STL/CC/fm-level$", "Mould level fluctuation"),
    ("box/fm-level", r"knowledge/STL/CC/fm-level$", "Mould level fluctuation"),
    ("box/d-sliver", r"cpl/STL/d-sliver$", "Sliver lines"),
    ("fmea/STL/CC?box=fm-level&release=v3", r"fmea/STL/CC\?box=fm-level&release=v3$", "FMEA v3"),
    ("cpl/STL/d-sliver", r"cpl/STL/d-sliver$", "Sliver lines"),
    ("cpl/STL/d-sliver/fm-level?process=CC", r"fm-level\?process=CC$", "How it leads to sliver"),
    ("t/104", r"t/104$", "Root-cause analysis of surface defects on line 2"),
]


@pytest.mark.parametrize(("link", "lands", "shows"), LINKS, ids=[link for link, _, _ in LINKS])
def test_every_link_opens_its_object(
    live_server: str, browser: Browser, link: str, lands: str, shows: str
) -> None:
    context = browser.new_context()
    page = context.new_page()
    page.goto(f"{live_server}{link}")
    expect(page).to_have_url(re.compile(lands))
    expect(page.locator("#content").get_by_text(shows).first).to_be_visible()
    context.close()


def test_a_box_that_does_not_exist(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}box/no-such-box")
    expect(page.get_by_role("heading", name="This box does not exist")).to_be_visible()
