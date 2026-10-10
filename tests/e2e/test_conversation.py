"""The task conversation in a real browser (milestone M7): reading, posting, images, editing."""

import re
from pathlib import Path

from playwright.sync_api import Page, expect

from taskboard.services.sample_data import defect_map_png
from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in


def open_conversation(page: Page, live_server: str, key: str = "104") -> None:
    page.goto(f"{live_server}t/{key}/conversation")
    expect(page.locator(".timeline")).to_be_visible()


def test_reading_the_sample_conversation(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}t/104")
    page.get_by_role("link", name="Conversation").click()
    expect(page).to_have_url(f"{live_server}t/104/conversation")
    expect(page.locator(".tab__count")).to_have_text("4")
    expect(page.locator(".event-line")).to_contain_text(
        "Anna Claes moved this from Idea to Started"
    )
    posts = page.locator(".post")
    expect(posts).to_have_count(4)
    first = posts.first
    expect(first.locator(".update-badge")).to_have_text("Update")
    expect(first.locator("strong").first).to_have_text("Week 38 status")
    image = first.locator(".md img")
    expect(image).to_have_attribute("alt", "defect map")
    assert image.evaluate("img => img.complete && img.naturalWidth > 0")
    expect(posts.nth(2).locator(".mention")).to_have_text("@Anna")
    expect(page.locator(".composer")).to_have_count(0)  # visitors only read
    assert console_errors == []


def test_updates_only(live_server: str, page: Page) -> None:
    open_conversation(page, live_server)
    page.get_by_role("button", name="Updates only").click()
    expect(page.locator(".post")).to_have_count(1)
    expect(page.locator(".event-line")).to_have_count(0)
    page.get_by_role("button", name="All").click()
    expect(page.locator(".post")).to_have_count(4)


def test_a_task_reference_opens_that_task(live_server: str, page: Page) -> None:
    page.goto(f"{live_server}priority")
    page.get_by_role("link", name="Root-cause analysis of surface defects on line 2").click()
    page.get_by_role("link", name="Conversation").click()
    page.locator(".md .task-ref", has_text="T-117").click()
    expect(page).to_have_url(f"{live_server}t/117")
    expect(page.locator(".drawer .task-panel__key")).to_have_text("T-117")


def test_an_image_opens_full_size_over_the_page_and_a_click_closes_it(
    live_server: str, page: Page, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    page.get_by_role("link", name="Root-cause analysis of surface defects on line 2").click()
    drawer = page.get_by_role("dialog", name="Task 104")
    drawer.get_by_role("link", name="Conversation").click()
    thumbnail = drawer.locator(".md img").first
    lightbox = page.get_by_role("dialog", name="Image: defect map")

    thumbnail.click()
    expect(lightbox).to_be_visible()
    image = lightbox.get_by_role("img", name="defect map")
    expect(image).to_have_attribute("src", re.compile(r"/api/attachments/[0-9a-f]{32}/"))
    # Full size: the 520 by 200 pixel sample is shown as is, not scaled down to fit a post.
    assert image.evaluate("img => img.complete && img.width === img.naturalWidth")
    image.click()  # a click on the image itself closes it
    expect(lightbox).to_have_count(0)
    expect(drawer).to_be_visible()

    thumbnail.click()
    expect(lightbox).to_be_visible()
    page.mouse.click(8, 8)  # so does a click beside it
    expect(lightbox).to_have_count(0)

    thumbnail.click()
    expect(lightbox).to_be_visible()
    page.keyboard.press("Escape")  # and Escape, which leaves the drawer open
    expect(lightbox).to_have_count(0)
    expect(drawer).to_be_visible()
    assert console_errors == []


def test_post_an_update_with_formatting_preview_and_an_image(
    live_server: str, page: Page, tmp_path: Path, console_errors: list[str]
) -> None:
    open_conversation(page, live_server)
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    box = page.get_by_role("textbox", name="Write a comment")
    box.fill("Grinding reports attached. Roll 7 shows the same chatter marks")
    box.press("End")
    page.keyboard.press("Shift+Home")
    page.get_by_role("button", name="Bold").click()
    expect(box).to_have_value("**Grinding reports attached. Roll 7 shows the same chatter marks**")

    image = tmp_path / "roll7-marks.png"
    image.write_bytes(defect_map_png(60, 30))
    page.locator(".composer input[type=file]").set_input_files(str(image))
    expect(page.locator(".file-chip")).to_contain_text("roll7-marks.png")
    # The image goes on its own line after the bold line, never inside the ** markers.
    expect(box).to_have_value(
        re.compile(
            r"^\*\*Grinding reports attached\. Roll 7 shows the same chatter marks\*\*\n"
            r"!\[roll7-marks\.png\]\(api/attachments/[0-9a-f]{32}/roll7-marks\.png\)$"
        )
    )

    page.get_by_role("button", name="Preview").click()
    expect(page.locator(".composer__preview strong")).to_have_text(
        "Grinding reports attached. Roll 7 shows the same chatter marks"
    )
    expect(page.locator(".composer__preview img")).to_be_visible()
    page.get_by_role("button", name="Write").click()

    page.get_by_label("Post as status update").check()
    page.get_by_role("button", name="Post", exact=True).click()
    newest = page.locator(".post").last
    expect(newest.locator(".update-badge")).to_be_visible()
    expect(newest.locator(".md img")).to_be_visible()
    expect(page.locator(".tab__count")).to_have_text("5")
    expect(box).to_have_value("")
    assert console_errors == []


def test_edit_and_delete_your_own_post(live_server: str, page: Page) -> None:
    open_conversation(page, live_server, "117")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.get_by_role("textbox", name="Write a comment").fill("First thought")
    page.get_by_role("textbox", name="Write a comment").press("Control+Enter")
    expect(page.locator(".post", has_text="First thought")).to_be_visible()
    post = page.locator(".post").last  # by position: while editing, its text is in a textarea

    post.get_by_role("button", name="Edit").click()
    editor = post.get_by_role("textbox", name="Write a comment")
    expect(editor).to_have_value("First thought")
    editor.fill("Second thought")
    post.get_by_role("button", name="Save").click()
    edited = page.locator(".post", has_text="Second thought")
    expect(edited.locator(".post__time")).to_contain_text("edited")

    page.once("dialog", lambda d: d.accept())
    edited.get_by_role("button", name="Delete").click()
    expect(page.locator(".post")).to_have_count(0)
    expect(page.locator(".timeline__empty").or_(page.locator(".event-line").first)).to_be_visible()


def test_other_peoples_posts_cannot_be_edited(live_server: str, page: Page) -> None:
    open_conversation(page, live_server)
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    expect(page.locator(".post").first).to_be_visible()
    expect(page.locator(".post").get_by_role("button", name="Edit")).to_have_count(0)
