"""People lanes and the Projects view in a real browser (milestone M6)."""

from playwright.sync_api import Locator, Page, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in


def lane(page: Page, name: str) -> Locator:
    return page.get_by_role("region", name=name)


def ranks(lane_locator: Locator) -> Locator:
    return lane_locator.locator(".card__rank")


OUTLINE_TEXT = """rows => rows.map(row => [...row.querySelectorAll(
    '.outline-row__num, .outline-row__name, .outline-row__rank, .outline-row__title'
)].map(part => part.textContent.trim()).join(' '))"""


def outline_rows(page: Page) -> list[str]:
    """Outline rows as "number name" for sections and "#rank title" for tasks."""
    expect(page.locator(".outline-row").first).to_be_visible()
    return page.locator(".outline-row").evaluate_all(OUTLINE_TEXT)


# ---------------------------------------------------------------- people


def test_one_lane_per_person_with_lead_and_helping_cards(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}people")
    expect(page.locator(".lane")).to_have_count(6)
    anna = lane(page, "Anna Claes")
    expect(anna.locator(".lane__counts")).to_have_text("2 lead · 2 helping")
    expect(ranks(anna)).to_have_text(["#01", "#02", "#07", "#10"])
    expect(anna.locator(".card--lead")).to_have_count(2)
    expect(anna.locator(".card--helping")).to_have_count(2)

    page.get_by_role("button", name="Lead only").click()
    expect(ranks(anna)).to_have_text(["#01", "#10"])
    expect(anna.locator(".lane__counts")).to_have_text("2 lead · 2 helping")
    page.get_by_role("button", name="Lead + helping").click()

    page.get_by_role("searchbox", name="Search title or description").fill("coil")
    expect(ranks(anna)).to_have_text(["#10"])
    expect(lane(page, "Bram Peeters").locator(".card")).to_have_count(1)
    assert console_errors == []


def test_archived_tasks_only_on_request(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}people")
    eva = lane(page, "Eva Janssens")
    expect(ranks(eva)).to_have_text(["#05", "#10"])
    page.get_by_role("button", name="Show archived").click()
    expect(ranks(eva)).to_have_text(["#05", "#10", "#11"])


def test_dragging_within_a_lane_changes_the_team_ranking(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}people")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    anna = lane(page, "Anna Claes")
    source = anna.locator(".card").nth(3).bounding_box()  # #10 Audit of coil handling damage
    target = anna.locator(".card").nth(0).bounding_box()  # #01
    assert source and target
    page.mouse.move(source["x"] + 20, source["y"] + 30)
    page.mouse.down()
    page.mouse.move(source["x"] + 20, source["y"] + 20, steps=3)
    page.mouse.move(target["x"] + 20, target["y"] + 20, steps=10)
    page.mouse.up()
    expect(anna.locator(".card__title").first).to_have_text("Audit of coil handling damage")
    page.goto(f"{live_server}priority")
    expect(page.locator(".task-row .task-key").first).to_have_text("T-075")


def test_a_card_opens_its_task(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}people")
    lane(page, "Dries Wouters").get_by_role("link", name="Guard rail check at the coiler").click()
    expect(page).to_have_url(f"{live_server}t/110")
    expect(page.get_by_role("dialog", name="Task 110")).to_be_visible()


# ---------------------------------------------------------------- projects


def test_projects_unfold_as_numbered_outlines(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}projects")
    expect(page).to_have_url(f"{live_server}projects/ASQ")
    expect(page.get_by_role("heading", name="Action plan surface quality", level=1)).to_be_visible()
    expect(page.locator(".project-summary")).to_contain_text("6 open tasks in this project")
    expect(page.locator(".outline-row").first).to_contain_text("Measurement & inspection")
    assert outline_rows(page) == [
        "1 Measurement & inspection",
        "1.1 Inspection criteria",
        "#02 Agree inspection criteria with customer panel",
        "1.2 Camera system",
        "#06 Budget proposal for inline camera system",
        "2 Line 2 defects",
        "#10 Audit of coil handling damage",
        "2.1 Root cause",
        "#01 Root-cause analysis of surface defects on line 2",
        "2.2 Roll maintenance",
        "2.2.1 Grinding",
        "#03 Tonnage-based work-roll regrinding",
        "3 People & training",
        "#05 Operator training: defect classification",
    ]
    expect(page.locator(".outline-row", has_text="Budget proposal")).to_contain_text(
        "also in Projects 2026"
    )
    tree_counts = page.locator(".tree-item .tree-item__count").all_inner_texts()
    assert tree_counts[:9] == ["6", "2", "1", "1", "3", "1", "1", "1", "1"]
    assert console_errors == []


def test_selecting_a_section_shows_its_subtree(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/ASQ")
    page.locator(".tree-item", has_text="Roll maintenance").click()
    expect(page.get_by_role("heading", name="2.2 Roll maintenance")).to_be_visible()
    expect(page.get_by_role("navigation", name="Breadcrumb").get_by_role("link")).to_have_text(
        ["Action plan surface quality", "2 Line 2 defects", "2.2 Roll maintenance"]
    )
    assert outline_rows(page) == [
        "2.2 Roll maintenance",
        "2.2.1 Grinding",
        "#03 Tonnage-based work-roll regrinding",
    ]
    page.get_by_role("navigation", name="Breadcrumb").get_by_role(
        "link", name="2 Line 2 defects"
    ).click()
    expect(page.get_by_role("heading", name="2 Line 2 defects")).to_be_visible()


def test_archived_tasks_in_projects_only_on_request(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/ASQ")
    page.locator(".tree-item", has_text="People & training").click()
    expect(page.locator(".outline-row--task")).to_have_count(1)
    page.get_by_role("button", name="Show archived").click()
    expect(page.locator(".outline-row--task")).to_have_count(2)
    expect(page.locator(".outline-row--task").last).to_contain_text(
        "Clean up old non-conformance records"
    )


def test_visitors_cannot_change_projects(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/ASQ")
    expect(page.locator(".outline-row").first).to_be_visible()
    expect(page.get_by_role("button", name="Edit sections")).to_have_count(0)
    expect(page.get_by_role("button", name="Add task here")).to_have_count(0)
    expect(page.get_by_role("button", name="New project")).to_have_count(0)


def test_add_a_task_to_the_selected_section(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/P26")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.locator(".tree-item", has_text="SPC").click()
    page.get_by_role("button", name="Add task here").click()
    drawer = page.get_by_role("dialog", name="New task")
    expect(drawer.locator(".placement")).to_contain_text("2 Process › 2.2 SPC")
    drawer.get_by_label("Title").fill("Calibrate the thickness gauge")
    drawer.get_by_role("button", name="Create task").click()
    page.keyboard.press("Escape")
    expect(
        page.locator(".outline-row--task", has_text="Calibrate the thickness gauge")
    ).to_be_visible()


def test_edit_the_sections_of_a_project(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects/SAF")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="Edit sections").click()
    page.get_by_role("button", name="+ Add section").click()
    name = page.get_by_role("textbox", name="Name of section 2", exact=True)
    expect(name).to_have_value("New section")
    name.fill("Lifting")
    name.press("Enter")
    page.get_by_role("button", name="Add a subsection to 2").click()
    expect(page.get_by_role("textbox", name="Name of section 2.1", exact=True)).to_have_value(
        "New section"
    )
    page.get_by_role("button", name="Move 2 up", exact=True).click()
    expect(page.get_by_role("textbox", name="Name of section 1", exact=True)).to_have_value(
        "Lifting"
    )
    expect(page.get_by_role("textbox", name="Name of section 2.1", exact=True)).to_have_value(
        "Coiler"
    )

    page.once("dialog", lambda d: d.accept())
    page.get_by_role("button", name="Delete 1.1", exact=True).click()
    expect(page.locator(".section-edit")).to_have_count(3)
    page.get_by_role("button", name="Done").click()
    expect(page.locator(".outline-row__name")).to_have_text(
        ["Lifting", "Machine guarding", "Coiler"]
    )


def test_create_a_project(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}projects")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("button", name="New project").click()
    dialog = page.get_by_role("dialog", name="New project")
    dialog.get_by_label("Name").fill("Energy 2027")
    dialog.get_by_label("Short key (2–10 letters or digits)").fill("en27")
    dialog.get_by_role("button", name="#1F7A6E").click()
    dialog.get_by_role("button", name="Create project").click()
    expect(page).to_have_url(f"{live_server}projects/EN27")
    expect(page.get_by_role("heading", name="Energy 2027", level=1)).to_be_visible()
    expect(page.locator(".sidebar").get_by_role("link", name="Energy 2027")).to_be_visible()
