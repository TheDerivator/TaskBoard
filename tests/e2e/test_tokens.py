"""API tokens in a real browser (D-097): create one on the profile page, let an "agent" use it, see
its posts marked "via" the token, revoke it; the agent guide downloads."""

import re

from playwright.sync_api import Page, Playwright, expect

from tests.conftest import TEST_ADMIN_PASSWORD
from tests.e2e.conftest import log_in


def test_a_token_from_the_profile_page(
    live_server: str, page: Page, playwright: Playwright, console_errors: list[str]
) -> None:
    page.goto(f"{live_server}priority")
    log_in(page, "admin", TEST_ADMIN_PASSWORD)
    page.locator(".sidebar__user").click()
    expect(page).to_have_url(re.compile(r"/profile$"))
    expect(page.get_by_role("heading", level=1, name="Profile")).to_be_visible()
    expect(page.get_by_role("cell", name="No tokens yet.")).to_be_visible()

    page.get_by_role("button", name="New token").click()
    dialog = page.get_by_role("dialog", name="New API token")
    dialog.get_by_label("Name").fill("Claude Code")
    dialog.get_by_label(re.compile("Read and write")).check()
    dialog.get_by_label("Expires after").select_option(label="30 days")
    dialog.get_by_role("button", name="Create token").click()

    shown = page.get_by_role("dialog", name="Your new token")
    secret = shown.get_by_test_id("token-secret").inner_text()
    assert re.fullmatch(r"tb_[A-Za-z0-9_-]{40,}", secret)
    expect(shown).to_contain_text(f'$env:TASKBOARD_TOKEN = "{secret}"')
    with page.expect_download() as download:
        shown.get_by_role("link", name="Download the agent guide").click()
    assert download.value.suggested_filename == "taskboard-agent-guide.md"
    guide = download.value.path().read_text(encoding="utf-8")
    assert "Authorization: Bearer" in guide and secret not in guide
    shown.get_by_role("button", name="Done").click()

    row = page.get_by_role("row", name=re.compile("Claude Code"))
    expect(row).to_contain_text("Read and write")
    expect(row).to_contain_text("Never used")

    # The agent: a client of its own, without the browser's cookies; only the token.
    agent = playwright.request.new_context()
    response = agent.post(
        f"{live_server}api/tasks/T-104/posts",
        headers={"Authorization": f"Bearer {secret}"},
        data={"body_md": "Summary from the agent."},
    )
    assert response.status == 201, response.text()

    page.goto(f"{live_server}t/104/conversation")
    posts = page.get_by_role("article", name=re.compile("Post by"))
    post = posts.filter(has_text="Summary from the agent.")
    expect(post.locator(".via-badge")).to_have_text("via Claude Code")

    page.goto(f"{live_server}profile")
    expect(row).to_contain_text("Last used")
    page.once("dialog", lambda confirm: confirm.accept())
    row.get_by_role("button", name="Revoke").click()
    expect(page.get_by_role("cell", name="No tokens yet.")).to_be_visible()
    refused = agent.get(f"{live_server}api/auth/me", headers={"Authorization": f"Bearer {secret}"})
    assert refused.status == 401
    agent.dispose()
    assert console_errors == []
