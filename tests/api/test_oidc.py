"""SSO with OpenID Connect against an in-process provider (milestone M9 acceptance).

A pre-provisioned account signs in and gets exactly its rights; unknown accounts follow the
configured policy; suspended accounts are refused; every token and flow check is exercised.
"""

from collections.abc import Generator, Iterator
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import update

from taskboard.config import Settings, UnknownUserPolicy
from taskboard.db.models import User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.providers import IdentityProviders
from taskboard.web import create_app
from tests.api.conftest import Ids
from tests.conftest import start_client
from tests.fake_idp import FakeIdentityProvider, fake_oidc_provider, new_key
from tests.helpers import login, make_user, section_id

JAN = {"oid": "oid-jan", "email": "jan.peeters@example.com", "name": "Jan Peeters"}


@pytest.fixture
def idp() -> FakeIdentityProvider:
    return FakeIdentityProvider()


def _client(settings: Settings, idp: FakeIdentityProvider) -> Generator[TestClient]:
    providers = IdentityProviders(redirect={"entra": fake_oidc_provider(idp)})
    yield from start_client(create_app(settings, providers=providers))


@pytest.fixture
def client(
    settings: Settings, sample_database: Database, idp: FakeIdentityProvider
) -> Iterator[TestClient]:
    del sample_database
    yield from _client(settings, idp)


@pytest.fixture
def jan(sample_database: Database) -> None:
    """Pre-provisioned by an administrator: pending, no password, Editor on Coatings."""
    with sample_database.new_session(write=True) as s:
        make_user(
            s,
            "jan.peeters",
            password=None,
            email="Jan.Peeters@example.com",
            status=UserStatus.PENDING,
            roles=[(BuiltinRole.EDITOR, Scope.section(section_id(s, "Coatings")))],
        )


def sign_in(
    client: TestClient, idp: FakeIdentityProvider, next_path: str = "/t/130", /, **claims: object
):
    start = client.get(
        "/api/auth/sso/entra/start", params={"next": next_path}, follow_redirects=False
    )
    assert start.status_code == 303, start.text
    answer = idp.approve(start.headers["location"], **(claims or JAN))
    return client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)


def error_of(response) -> str:
    location = response.headers["location"]
    assert location.startswith("/?sso_error="), location
    return location


# ---------------------------------------------------------------- the happy path


def test_the_login_options_list_the_provider(client: TestClient) -> None:
    assert client.get("/api/auth/me").json()["login"]["providers"] == [
        {"name": "entra", "display_name": "Microsoft"}
    ]


def test_start_sends_the_browser_to_the_provider_with_pkce_and_nonce(client: TestClient) -> None:
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    location = start.headers["location"]
    assert location.startswith("https://idp.example.test/tenant/v2.0/authorize?")
    for part in (
        "response_type=code",
        "client_id=taskboard-tests",
        "code_challenge_method=S256",
        "nonce=",
        "state=",
    ):
        assert part in location
    assert "redirect_uri=http%3A%2F%2Ftestserver%2Fapi%2Fauth%2Fsso%2Fentra%2Fcallback" in location
    assert "taskboard_sso_state=" in start.headers["set-cookie"]


def test_a_pre_provisioned_account_signs_in_with_its_prepared_rights(
    client: TestClient, idp: FakeIdentityProvider, jan: None, ids: Ids
) -> None:
    del jan
    done = sign_in(client, idp)
    assert done.status_code == 303
    assert done.headers["location"] == "/t/130"  # back where the sign-in started
    me = client.get("/api/auth/me").json()
    assert (me["username"], me["is_anonymous"]) == ("jan.peeters", False)
    assert me["permissions"]["task.edit"] == {
        "everywhere": False,
        "section_ids": [ids.sections["Coatings"]],
    }
    # The account is now active and linked; the next sign-in finds it by subject.
    client.post("/api/auth/logout")
    assert (
        sign_in(client, idp, oid="oid-jan", email="renamed@example.com").headers["location"]
        == "/t/130"
    )
    assert client.get("/api/auth/me").json()["username"] == "jan.peeters"


# ---------------------------------------------------------------- policies


def test_unknown_people_are_rejected_by_default(
    client: TestClient, idp: FakeIdentityProvider
) -> None:
    location = error_of(sign_in(client, idp, oid="oid-x", email="stranger@example.com"))
    assert "no%20account%20has%20been%20set%20up" in location
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_unknown_people_can_be_created_without_rights(
    settings: Settings, sample_database: Database, idp: FakeIdentityProvider
) -> None:
    del sample_database
    settings = settings.model_copy(update={"sso_unknown_users": UnknownUserPolicy.CREATE})
    clients = _client(settings, idp)
    client = next(clients)
    sign_in(client, idp, oid="oid-new", email="new.person@example.com", name="New Person")
    me = client.get("/api/auth/me").json()
    assert (me["username"], me["display_name"]) == ("new.person@example.com", "New Person")
    assert me["permissions"]["task.edit"]["section_ids"] == []
    clients.close()


def test_suspended_accounts_are_refused(
    client: TestClient, idp: FakeIdentityProvider, jan: None, sample_database: Database
) -> None:
    del jan
    sign_in(client, idp)
    client.post("/api/auth/logout")
    with sample_database.session(write=True) as s:
        s.execute(
            update(User).where(User.username == "jan.peeters").values(status=UserStatus.SUSPENDED)
        )
    assert "suspended" in error_of(sign_in(client, idp))


# ---------------------------------------------------------------- flow and token checks


def test_the_callback_must_come_back_to_the_browser_that_started(
    settings: Settings, sample_database: Database, idp: FakeIdentityProvider, jan: None
) -> None:
    del sample_database, jan
    attacker_clients, victim_clients = _client(settings, idp), _client(settings, idp)
    attacker, victim = next(attacker_clients), next(victim_clients)
    start = attacker.get("/api/auth/sso/entra/start", follow_redirects=False)
    answer = idp.approve(start.headers["location"], **JAN)
    # The attacker lures the victim to the callback with their own code and state (login CSRF).
    response = victim.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)
    assert "not%20started%20in%20this%20browser" in error_of(response)
    assert victim.get("/api/auth/me").json()["is_anonymous"] is True
    attacker_clients.close()
    victim_clients.close()


def test_a_callback_cannot_be_replayed(
    client: TestClient, idp: FakeIdentityProvider, jan: None
) -> None:
    del jan
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    answer = idp.approve(start.headers["location"], **JAN)
    client.cookies.set("taskboard_sso_state", answer["state"])
    assert (
        client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False).headers[
            "location"
        ]
        == "/"
    )
    client.post("/api/auth/logout")
    client.cookies.set("taskboard_sso_state", answer["state"])
    again = client.get("/api/auth/sso/entra/callback", params=answer, follow_redirects=False)
    assert "expired" in error_of(again)


@pytest.mark.parametrize(
    ("tamper", "message"),
    [
        (lambda idp: setattr(idp, "token_audience", "someone-else"), "not%20valid"),
        (lambda idp: setattr(idp, "token_lifetime", -120), "not%20valid"),
        (lambda idp: setattr(idp, "nonce_override", "another-sign-in"), "nonce"),
        (
            lambda idp: setattr(idp, "sign_with", new_key()),
            "not%20valid",
        ),
    ],
    ids=["wrong audience", "expired", "wrong nonce", "forged signature"],
)
def test_bad_tokens_are_refused(
    client: TestClient, idp: FakeIdentityProvider, jan: None, tamper, message: str
) -> None:
    del jan
    tamper(idp)
    assert message in error_of(sign_in(client, idp))
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_key_rotation_is_followed(client: TestClient, idp: FakeIdentityProvider, jan: None) -> None:
    del jan
    sign_in(client, idp)
    client.post("/api/auth/logout")
    idp.rotate_keys()
    assert sign_in(client, idp).headers["location"] == "/t/130"


def test_the_provider_refusing_is_reported(client: TestClient) -> None:
    start = client.get("/api/auth/sso/entra/start", follow_redirects=False)
    state = start.headers["location"].split("state=")[1].split("&")[0]
    response = client.get(
        "/api/auth/sso/entra/callback",
        params={"state": state, "error": "access_denied"},
        follow_redirects=False,
    )
    assert "access_denied" in error_of(response)


def test_no_open_redirects(client: TestClient, idp: FakeIdentityProvider, jan: None) -> None:
    del jan
    for evil in ("https://evil.example.com/", "//evil.example.com", "/\\evil"):
        assert sign_in(client, idp, evil).headers["location"] == "/"
        client.post("/api/auth/logout")


def test_unknown_providers(client: TestClient) -> None:
    assert client.get("/api/auth/sso/github/start", follow_redirects=False).status_code == 404


# ---------------------------------------------------------------- group mappings


def test_group_membership_grants_roles_while_it_lasts(
    client: TestClient, idp: FakeIdentityProvider, jan: None, ids: Ids, sample_database: Database
) -> None:
    del jan
    admin_clients = start_client(cast(FastAPI, client.app))  # a second browser, same app
    admin = next(admin_clients)
    login(admin, "admin", "admin-password-for-tests")
    roles = {r["key"]: r["id"] for r in admin.get("/api/admin/roles").json()}
    mapping = admin.post(
        "/api/admin/group-mappings",
        json={
            "provider": "entra",
            "group_name": "g-quality",
            "role_id": roles["editor"],
            "scope": "section",
            "scope_id": ids.sections["Quality"],
        },
    )
    assert mapping.status_code == 201 and mapping.json()["scope_label"] == "STL · Quality"
    assert (
        admin.post(
            "/api/admin/group-mappings", json=mapping.json() | {"scope": "section"}
        ).status_code
        == 409
    )

    sign_in(client, idp, **(JAN | {"groups": ["g-quality", "g-other"]}))
    edit = client.get("/api/auth/me").json()["permissions"]["task.edit"]["section_ids"]
    assert sorted(edit) == sorted([ids.sections["Coatings"], ids.sections["Quality"]])

    client.post("/api/auth/logout")
    sign_in(client, idp, **(JAN | {"groups": []}))  # left the group at the provider
    assert client.get("/api/auth/me").json()["permissions"]["task.edit"]["section_ids"] == [
        ids.sections["Coatings"]
    ]

    listed = admin.get("/api/admin/group-mappings").json()
    assert [(m["group_name"], m["role_name"]) for m in listed] == [("g-quality", "Editor")]
    assert admin.delete(f"/api/admin/group-mappings/{listed[0]['id']}").status_code == 204
    admin_clients.close()
