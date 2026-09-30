"""Windows sign-in by the app itself (HTTP Negotiate): challenges, the handshake, the session."""

import base64
import sys
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response

from taskboard.config import Settings, UnknownUserPolicy
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.providers import IdentityProviders, NegotiateIdentityProvider
from taskboard.identity.providers.negotiate import NegotiateProvider
from taskboard.web import create_app
from taskboard.web.csrf import CSRF_HEADER
from tests.api.conftest import Ids
from tests.conftest import start_client
from tests.fake_negotiate import (
    LAST_WORD,
    NTLM_CHALLENGE,
    NTLM_HELLO,
    NTLM_WRONG_PASSWORD,
    FakeContext,
    ntlm_proof,
    ticket,
)
from tests.helpers import make_user, section_id

JDOE = "CORP\\JDoe"
URL = "/api/auth/windows"


def _client(
    settings: Settings, provider: NegotiateIdentityProvider | None = None
) -> Generator[TestClient]:
    provider = provider or NegotiateProvider(new_context=FakeContext)
    yield from start_client(create_app(settings, providers=IdentityProviders(negotiate=provider)))


def negotiate(client: TestClient, token: bytes) -> Response:
    """What a browser sends in answer to a challenge."""
    header = f"Negotiate {base64.b64encode(token).decode()}"
    return client.post(URL, headers={"Authorization": header})


def answer(response: Response) -> bytes:
    """The token in the response's `WWW-Authenticate: Negotiate <token>`."""
    scheme, _, value = response.headers["www-authenticate"].partition(" ")
    assert scheme == "Negotiate"
    return base64.b64decode(value)


@pytest.fixture
def windows(settings: Settings, sample_database: Database) -> Generator[TestClient]:
    """The sample board with Windows sign-in on, and an account prepared for CORP\\JDoe."""
    with sample_database.new_session(write=True) as s:
        make_user(
            s,
            "jdoe",
            password=None,
            status=UserStatus.PENDING,
            roles=[(BuiltinRole.EDITOR, Scope.section(section_id(s, "Process")))],
        )
    yield from _client(settings)


def test_it_is_off_unless_configured(board: TestClient) -> None:
    assert board.post(URL).status_code == 405  # no such route: only the page's GET fallback
    assert board.get(URL).status_code == 404
    assert board.get("/api/auth/me").json()["login"]["windows"] is None


def test_the_page_is_told_to_try_by_itself(windows: TestClient) -> None:
    assert windows.get("/api/auth/me").json()["login"]["windows"] == {"automatic": True}


def test_the_page_can_be_told_to_wait_for_a_click(
    settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = _client(settings, NegotiateProvider(automatic=False, new_context=FakeContext))
    client = next(clients)
    assert client.get("/api/auth/me").json()["login"]["windows"] == {"automatic": False}
    clients.close()


@pytest.mark.parametrize("authorization", [None, "Basic amRvZTpwdw==", "Negotiate", "Negotiate ?"])
def test_a_request_without_a_token_is_challenged(
    windows: TestClient, authorization: str | None
) -> None:
    response = windows.post(URL, headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Negotiate"
    assert response.json()["error"] == "windows_sign_in_required"
    assert "taskboard_session" not in response.cookies


def test_a_kerberos_ticket_signs_in_with_one_request(windows: TestClient, ids: Ids) -> None:
    response = negotiate(windows, ticket(JDOE))
    assert response.status_code == 200, response.text
    assert answer(response) == LAST_WORD  # the browser checks the server in turn
    assert response.json()["username"] == "jdoe"
    # From here on it is an ordinary session: the cookie identifies the user...
    me = windows.get("/api/auth/me").json()
    assert (me["username"], me["is_anonymous"], me["signed_in_by"]) == ("jdoe", False, None)
    assert me["permissions"]["task.edit"]["section_ids"] == [ids.sections["Process"]]
    # ...who can log out, e.g. to use the built-in admin account.
    assert windows.post("/api/auth/logout").status_code == 204
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_ntlm_signs_in_with_two_requests(windows: TestClient) -> None:
    first = negotiate(windows, NTLM_HELLO)
    assert first.status_code == 401
    assert answer(first) == NTLM_CHALLENGE
    second = negotiate(windows, ntlm_proof(JDOE))
    assert second.status_code == 200, second.text
    assert "www-authenticate" not in second.headers
    assert windows.get("/api/auth/me").json()["username"] == "jdoe"


def test_a_refused_token_is_challenged_again(windows: TestClient) -> None:
    """So the browser can ask for a user name and password, as with any Windows-protected site."""
    negotiate(windows, NTLM_HELLO)
    response = negotiate(windows, NTLM_WRONG_PASSWORD)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Negotiate"
    assert response.json()["error"] == "windows_sign_in_required"
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_someone_without_an_account_is_refused_without_a_new_challenge(
    windows: TestClient,
) -> None:
    response = negotiate(windows, ticket("CORP\\Stranger"))
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"
    assert "no account has been set up for you" in response.json()["message"]
    assert "www-authenticate" not in response.headers  # asking again would not help
    assert windows.get("/api/auth/me").json()["is_anonymous"] is True


def test_unknown_people_can_get_an_account_without_rights(
    settings: Settings, sample_database: Database
) -> None:
    del sample_database
    clients = _client(settings.model_copy(update={"sso_unknown_users": UnknownUserPolicy.CREATE}))
    client = next(clients)
    me = negotiate(client, ticket("CORP\\Stranger")).json()
    assert (me["username"], me["display_name"], me["is_anonymous"]) == (
        "stranger",
        "Stranger",
        False,
    )
    assert me["permissions"]["task.edit"] == {"everywhere": False, "section_ids": []}
    clients.close()


def test_a_suspended_account_is_refused(windows: TestClient, sample_database: Database) -> None:
    with sample_database.new_session(write=True) as s:
        make_user(s, "anna", password=None, status=UserStatus.SUSPENDED)
    response = negotiate(windows, ticket("CORP\\Anna"))
    assert response.status_code == 403
    assert response.json()["message"] == "this account is suspended"


def test_signing_in_needs_the_csrf_header(windows: TestClient) -> None:
    del windows.headers[CSRF_HEADER]
    response = negotiate(windows, ticket(JDOE))
    assert (response.status_code, response.json()["error"]) == (403, "csrf_failed")


@pytest.mark.skipif(sys.platform != "win32", reason="needs Windows SSPI")
def test_a_real_windows_handshake_signs_in_whoever_runs_the_tests(
    settings: Settings, sample_database: Database
) -> None:
    """No fakes: pyspnego's client plays the browser, and Windows itself checks the tokens."""
    import spnego
    from spnego.exceptions import SpnegoError

    del sample_database
    settings = settings.model_copy(
        update={"windows_auth": True, "sso_unknown_users": UnknownUserPolicy.CREATE}
    )
    clients = start_client(create_app(settings))  # providers from the settings, like production
    client = next(clients)
    browser = spnego.client(hostname="localhost", service="HTTP", protocol="negotiate")
    try:
        token = browser.step()
    except SpnegoError as error:  # pragma: no cover  (an account Windows gives no credentials)
        pytest.skip(f"this Windows account cannot start a handshake: {error}")
    response = negotiate(client, token or b"")
    for _ in range(3):
        if response.status_code != 401:
            break
        token = browser.step(answer(response))
        response = negotiate(client, token or b"")
    assert response.status_code == 200, response.text
    if "www-authenticate" in response.headers:
        browser.step(answer(response))
    assert browser.complete
    me = client.get("/api/auth/me").json()
    assert me["is_anonymous"] is False
    assert me["username"] and "\\" not in me["username"]  # CORP\jdoe → jdoe
    clients.close()
