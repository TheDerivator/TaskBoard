"""Browser tests: a real server on a free port with the sample board, driven by Playwright.

Run with `uv run pytest -m e2e` (or `uv run python scripts/check.py --e2e`). Needs Chromium once:
`uv run playwright install chromium`.
"""

import gc
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import ConsoleMessage, Page
from starlette.types import ASGIApp

from taskboard.config import Settings
from taskboard.db.session import Database
from taskboard.web import create_app

E2E_DIR = Path(__file__).resolve().parent


# When a browser drops a connection mid-request (a view navigates while its fetches are still in
# flight), Windows' asyncio proactor in the test server's thread may leave that socket for the
# garbage collector, which warns. Harmless, and not the app's code: only these two are ignored.
SERVER_SOCKET_FINALIZERS = (
    "ignore:Exception ignored while finalizing socket:pytest.PytestUnraisableExceptionWarning",
    "ignore:Exception ignored while calling deallocator <function _ProactorBasePipeTransport"
    ":pytest.PytestUnraisableExceptionWarning",
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).parents:
            item.add_marker(pytest.mark.e2e)
            for rule in SERVER_SOCKET_FINALIZERS:
                item.add_marker(pytest.mark.filterwarnings(rule))


@pytest.fixture
def live_server(settings: Settings, sample_database: Database) -> Iterator[str]:
    """Base URL (ending in "/") of a running server on a fresh copy of the sample board."""
    del sample_database  # loaded before the server starts
    yield from serve(create_app(settings))


def serve(app: ASGIApp) -> Iterator[str]:
    """Run `app` on a free port in a background thread; yields its base URL."""
    # Port 0: the OS picks a free port at bind time (no race with other processes).
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", proxy_headers=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the test server did not start")
        time.sleep(0.02)
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/"
    server.should_exit = True
    thread.join(timeout=10)
    # Finalize the server's leftover sockets now, while this test's warning filters apply, rather
    # than during whichever test the garbage collector happens to run in next.
    gc.collect()


@pytest.fixture
def console_errors(page: Page) -> list[str]:
    """JavaScript errors seen by the page; tests assert it stays empty.

    Failed HTTP responses (e.g. a deliberate wrong password) are logged by the browser too; tests
    check those responses themselves, so they are not counted here.
    """
    errors: list[str] = []

    def on_console(message: ConsoleMessage) -> None:
        if message.type == "error" and not message.text.startswith("Failed to load resource"):
            errors.append(message.text)

    page.on("console", on_console)
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_default_timeout(10_000)
    return errors


def log_in(page: Page, username: str, password: str) -> None:
    """Log in through the sidebar's login dialog and wait until it has closed."""
    page.locator(".sidebar").get_by_role("button", name="Log in").click()
    dialog = page.get_by_role("dialog", name="Log in")
    dialog.get_by_label("Username").fill(username)
    dialog.get_by_label("Password").fill(password)
    dialog.get_by_role("button", name="Log in").click()
    dialog.wait_for(state="detached")
