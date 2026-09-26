"""SSO through a trusted reverse proxy header (e.g. IIS Windows authentication)."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from taskboard.config import Settings
from taskboard.db.models import GroupRoleMapping, Role
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.providers import IdentityProviders
from taskboard.web import create_app
from tests.api.conftest import Ids
from tests.conftest import start_client
from tests.helpers import make_user, section_id

HEADERS = {"X-Remote-User": "CORP\\JDoe", "X-Remote-Name": "John Doe"}


def _client(settings: Settings, **overrides: object) -> Generator[TestClient]:
    settings = settings.model_copy(
        update={
            "trusted_header": "X-Remote-User",
            "trusted_header_name": "X-Remote-Name",
            "trusted_header_groups": "X-Remote-Groups",
            "trusted_proxies": "testclient",  # the TestClient's address
        }
        | overrides
    )
    yield from start_client(
        create_app(settings, providers=IdentityProviders.from_settings(settings))
    )


@pytest.fixture
def jdoe(sample_database: Database) -> None:
    """Pre-provisioned by username (Windows logins usually carry no email)."""
    with sample_database.new_session(write=True) as s:
        make_user(
            s,
            "jdoe",
            password=None,
            status=UserStatus.PENDING,
            roles=[(BuiltinRole.EDITOR, Scope.section(section_id(s, "Process")))],
        )


def test_the_proxy_identifies_a_pre_provisioned_account(
    settings: Settings, jdoe: None, ids: Ids
) -> None:
    del jdoe
    clients = _client(settings)
    client = next(clients)
    me = client.get("/api/auth/me", headers=HEADERS).json()
    assert me["username"] == "jdoe"
    assert me["signed_in_by"] == "Windows sign-in"  # so the page offers no "Log out"
    assert me["permissions"]["task.edit"]["section_ids"] == [ids.sections["Process"]]
    # Without the header (the proxy did not authenticate) the visitor is anonymous.
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    clients.close()


def test_headers_from_anyone_but_the_proxy_are_ignored(settings: Settings, jdoe: None) -> None:
    del jdoe
    clients = _client(settings, trusted_proxies="10.0.0.5")
    client = next(clients)
    assert client.get("/api/auth/me", headers=HEADERS).json()["is_anonymous"] is True
    clients.close()


def test_the_proxy_may_forward_the_client_address(settings: Settings, jdoe: None) -> None:
    """IIS ARR adds X-Forwarded-For (with the client's port); the proxy still vouches."""
    del jdoe
    clients = _client(settings)
    client = next(clients)
    forwarded = HEADERS | {"X-Forwarded-For": "203.0.113.5:51234", "X-Forwarded-Proto": "https"}
    assert client.get("/api/auth/me", headers=forwarded).json()["username"] == "jdoe"
    clients.close()


def test_group_headers_feed_group_mappings(
    settings: Settings, jdoe: None, ids: Ids, sample_database: Database
) -> None:
    del jdoe
    with sample_database.session(write=True) as s:
        mapping = GroupRoleMapping(
            provider="proxy",
            group_name="STL-Maintenance",
            role=s.scalars(select(Role).where(Role.key == "editor")).one(),
        )
        mapping.scope = Scope.section(ids.sections["Maintenance"])
        s.add(mapping)
    clients = _client(settings)
    client = next(clients)
    me = client.get(
        "/api/auth/me", headers=HEADERS | {"X-Remote-Groups": "STL-Maintenance, Everyone"}
    ).json()
    assert sorted(me["permissions"]["task.edit"]["section_ids"]) == sorted(
        [ids.sections["Process"], ids.sections["Maintenance"]]
    )
    clients.close()


def test_the_domain_can_be_kept_in_the_username(
    settings: Settings, sample_database: Database
) -> None:
    with sample_database.new_session(write=True) as s:
        make_user(s, "corp\\jdoe", password=None, status=UserStatus.PENDING)
    clients = _client(settings, trusted_header_strip_domain=False)
    client = next(clients)
    assert client.get("/api/auth/me", headers=HEADERS).json()["username"] == "corp\\jdoe"
    clients.close()
