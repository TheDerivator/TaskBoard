"""X-Forwarded-For/-Proto: believed only from trusted proxies, which are remembered."""

from collections.abc import Coroutine
from typing import Any

import pytest

from taskboard.api.client import PROXY_KEY, ForwardedHeadersMiddleware, TrustedProxies


def run(coroutine: Coroutine[Any, Any, None]) -> None:
    """Run a coroutine that never waits. (asyncio.run refuses to start beside Playwright's loop.)"""
    with pytest.raises(StopIteration):
        coroutine.send(None)


def scope_after(
    peer: str, headers: dict[str, str], trusted: str = "127.0.0.1,::1"
) -> dict[str, Any]:
    """The scope the app sees for a request from `peer` carrying `headers`."""
    seen: dict[str, Any] = {}

    async def app(scope: Any, receive: Any, send: Any) -> None:
        del receive, send
        seen.update(scope)

    scope: dict[str, Any] = {
        "type": "http",
        "scheme": "http",
        "client": (peer, 50000),
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
    }
    run(ForwardedHeadersMiddleware(app, TrustedProxies(trusted))(scope, None, None))  # type: ignore[arg-type]
    return seen


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),  # IPv4 on a dual-stack socket
        ("10.1.2.3", True),
        ("10.200.0.1", False),
        ("testclient", True),
        ("TestClient", True),
        ("192.0.2.1", False),
        ("", False),
        (None, False),
    ],
)
def test_trusted_proxies_are_addresses_networks_or_names(host: str | None, expected: bool) -> None:
    assert (host in TrustedProxies("127.0.0.1, ::1, 10.1.0.0/16, testclient")) is expected


def test_a_trusted_proxy_gives_the_client_address_and_scheme() -> None:
    scope = scope_after(
        "127.0.0.1", {"X-Forwarded-For": "203.0.113.5:51234", "X-Forwarded-Proto": "https"}
    )
    assert scope["client"] == ("203.0.113.5", 0)
    assert scope["scheme"] == "https"
    assert scope[PROXY_KEY] == "127.0.0.1"


def test_a_trusted_proxy_without_forwarded_headers_is_still_remembered() -> None:
    scope = scope_after("::1", {})
    assert scope["client"] == ("::1", 50000)
    assert scope[PROXY_KEY] == "::1"


def test_headers_from_anyone_else_are_ignored() -> None:
    scope = scope_after("192.0.2.1", {"X-Forwarded-For": "127.0.0.1", "X-Forwarded-Proto": "https"})
    assert scope["client"] == ("192.0.2.1", 50000)
    assert scope["scheme"] == "http"
    assert PROXY_KEY not in scope


def test_the_client_is_the_nearest_address_that_is_not_a_proxy() -> None:
    # The client claimed to be 198.51.100.7; the outer proxy (10.1.0.2) saw 203.0.113.5.
    scope = scope_after(
        "10.1.0.1",
        {"X-Forwarded-For": "198.51.100.7, 203.0.113.5, 10.1.0.2"},
        trusted="10.1.0.0/16",
    )
    assert scope["client"] == ("203.0.113.5", 0)


def test_bracketed_ipv6_with_port_and_unknown_schemes() -> None:
    scope = scope_after(
        "127.0.0.1", {"X-Forwarded-For": "[2001:db8::1]:443", "X-Forwarded-Proto": "gopher"}
    )
    assert scope["client"] == ("2001:db8::1", 0)
    assert scope["scheme"] == "http"


def test_other_scopes_pass_through_untouched() -> None:
    seen: list[dict[str, Any]] = []

    async def app(scope: Any, receive: Any, send: Any) -> None:
        del receive, send
        seen.append(scope)

    lifespan = {"type": "lifespan"}
    run(ForwardedHeadersMiddleware(app, TrustedProxies("127.0.0.1"))(lifespan, None, None))  # type: ignore[arg-type]
    assert seen == [{"type": "lifespan"}]
