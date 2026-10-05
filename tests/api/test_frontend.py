"""Serving the frontend: app routes return the page, base path injection, static caching,
security headers."""

import base64
import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from taskboard.config import Settings
from taskboard.db.session import Database
from taskboard.web import create_app, frontend


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/priority",
        "/people",
        "/people/STL/Quality",
        "/projects/ASQ",
        "/t/K7Q2MX",
        "/t/K7Q2MX/conversation",
        "/changes/STL/LM",
        "/changes/STL/LM/timeline",
        "/changes/STL/LM/LM-07/conversation",
        "/knowledge/STL/CC/fm-level",
        "/fmea/STL/CC",
        "/cpl/STL/sliver-lines",
    ],
)
def test_app_routes_serve_the_page(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert '<div id="app">' in response.text
    assert '<base href="/">' in response.text
    assert response.headers["cache-control"] == "no-cache"


def test_unknown_pages_still_render_the_app_with_404(client: TestClient) -> None:
    response = client.get("/no/such/page")
    assert response.status_code == 404
    assert '<div id="app">' in response.text


def test_unknown_api_paths_answer_json(client: TestClient) -> None:
    response = client.get("/api/no/such/endpoint")
    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


@pytest.mark.parametrize(
    ("configured", "expected"),
    [("/taskboard", "/taskboard/"), ("tasks/board/", "/tasks/board/"), ("", "/")],
)
def test_base_path_is_normalized_and_injected(
    settings: Settings, configured: str, expected: str
) -> None:
    app = create_app(settings.model_copy(update={"base_path": configured}))
    with TestClient(app) as client:
        assert f'<base href="{expected}">' in client.get("/priority").text


def test_static_files_are_revalidated(client: TestClient) -> None:
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert "javascript" in response.headers["content-type"]


def test_vendored_libraries_and_fonts_are_served(client: TestClient) -> None:
    for path in (
        "/static/vendor/preact/preact.module.js",
        "/static/vendor/preact/hooks.module.js",
        "/static/vendor/htm/htm.module.js",
        "/static/fonts/ibm-plex-sans-latin-400-normal.woff2",
        "/static/fonts/ibm-plex-mono-latin-600-normal.woff2",
    ):
        assert client.get(path).status_code == 200, path


def test_security_headers_on_pages_and_api(client: TestClient) -> None:
    for path in ("/priority", "/api/health", "/static/js/main.js", "/api/no/such/endpoint"):
        headers = client.get(path).headers
        assert headers["x-content-type-options"] == "nosniff", path
        assert headers["x-frame-options"] == "DENY", path
        assert headers["referrer-policy"] == "same-origin", path
        assert "frame-ancestors 'none'" in headers["content-security-policy"], path


def test_the_policy_allows_exactly_the_pages_inline_import_map(client: TestClient) -> None:
    page = client.get("/priority")
    policy = dict(
        directive.strip().split(" ", 1)
        for directive in page.headers["content-security-policy"].split(";")
    )
    assert policy["default-src"] == "'none'"
    assert policy["style-src"] == "'self'"  # no inline styles
    [import_map] = re.findall(r'<script type="importmap">(.*?)</script>', page.text, re.DOTALL)
    digest = base64.b64encode(hashlib.sha256(import_map.encode()).digest()).decode()
    assert policy["script-src"] == f"'self' 'sha256-{digest}'"


def test_the_api_docs_keep_working(client: TestClient) -> None:
    """Swagger UI loads from a CDN and runs inline code: it gets no CSP (the rest still applies)."""
    headers = client.get("/api/docs").headers
    assert "content-security-policy" not in headers
    assert headers["x-content-type-options"] == "nosniff"


def test_large_responses_are_compressed(client: TestClient, sample_database: Database) -> None:
    del sample_database
    response = client.get("/api/tasks", headers={"Accept-Encoding": "gzip"})
    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["total"] == 11  # the client decompresses transparently


def test_the_server_serves_every_view_the_browser_router_knows() -> None:
    """Each first path segment parsed in static/js/lib/routes.js is an app route on the server,
    so pasted links answer 200 (not 404) for every view."""
    routes_js = Path(frontend.__file__).parent.parent / "static" / "js" / "lib" / "routes.js"
    heads = set(re.findall(r'head === "([a-z]+)"', routes_js.read_text(encoding="utf-8")))
    assert heads, "no route heads found in routes.js"
    assert heads <= frontend.APP_ROUTES
