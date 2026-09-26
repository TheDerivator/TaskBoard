"""SSO readiness: pre-provisioned accounts get exactly the rights an admin prepared.

Uses a fake *ambient* provider that trusts `X-Fake-Sub` / `X-Fake-Email` headers, standing in for
a real one (M9). The provisioning rules under test are the real ones.
"""

from collections.abc import Generator, Iterator, Mapping

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from taskboard.config import Settings, UnknownUserPolicy
from taskboard.db.models import AuditEntry, ExternalIdentity, User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.providers import ExternalIdentity as Identity
from taskboard.identity.providers import IdentityProviders
from taskboard.web import create_app
from tests.conftest import start_client
from tests.helpers import make_user, section_id


class FakeHeaderProvider:
    name = "fake"
    display_name = "Fake SSO"

    def identify(self, headers: Mapping[str, str], proxy: str | None) -> Identity | None:
        subject = headers.get("x-fake-sub")
        if not subject:
            return None
        return Identity(self.name, subject, email=headers.get("x-fake-email"), display_name=subject)


def sso(sub: str, email: str | None = None) -> dict[str, str]:
    return {"X-Fake-Sub": sub} | ({"X-Fake-Email": email} if email else {})


@pytest.fixture
def db(sample_database: Database) -> Iterator[Session]:
    with sample_database.new_session(write=True) as session:
        yield session


def _client(settings: Settings) -> Generator[TestClient]:
    app = create_app(settings, providers=IdentityProviders(ambient=[FakeHeaderProvider()]))
    yield from start_client(app)


@pytest.fixture
def sso_client(settings: Settings, db: Session) -> Iterator[TestClient]:
    del db  # sample data must be loaded before the app starts
    yield from _client(settings)


def test_a_pre_provisioned_account_gets_exactly_the_prepared_rights(
    sso_client: TestClient, db: Session
) -> None:
    coatings = section_id(db, "Coatings")
    make_user(
        db,
        "jan.peeters",
        password=None,
        email="Jan.Peeters@example.com",
        status=UserStatus.PENDING,
        roles=[(BuiltinRole.EDITOR, Scope.section(coatings))],
    )
    me = sso_client.get("/api/auth/me", headers=sso("oid-123", "jan.peeters@EXAMPLE.com")).json()
    assert me["username"] == "jan.peeters"
    assert me["permissions"]["task.edit"] == {"everywhere": False, "section_ids": [coatings]}

    db.expire_all()
    user = db.scalars(select(User).where(User.username == "jan.peeters")).one()
    assert user.status is UserStatus.ACTIVE
    assert [(i.provider, i.subject) for i in user.external_identities] == [("fake", "oid-123")]
    assert db.scalar(select(AuditEntry.action).where(AuditEntry.action == "user.sso_linked"))

    # Later requests are matched on the stable subject, even if the email claim changes.
    again = sso_client.get("/api/auth/me", headers=sso("oid-123", "renamed@example.com")).json()
    assert again["username"] == "jan.peeters"


def test_unknown_people_are_rejected_by_default(sso_client: TestClient) -> None:
    response = sso_client.get("/api/auth/me", headers=sso("oid-999", "stranger@example.com"))
    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_unknown_people_can_be_created_without_rights(settings: Settings, db: Session) -> None:
    del db  # sample data must be loaded before the app starts
    settings = settings.model_copy(update={"sso_unknown_users": UnknownUserPolicy.CREATE})
    clients = _client(settings)
    client = next(clients)
    me = client.get("/api/auth/me", headers=sso("oid-777", "new.person@example.com")).json()
    clients.close()
    assert me["username"] == "new.person@example.com"
    assert me["permissions"]["task.edit"] == {"everywhere": False, "section_ids": []}
    assert me["permissions"]["task.view"]["everywhere"] is True  # the anonymous floor


def test_suspended_accounts_are_refused_whatever_the_provider_says(
    sso_client: TestClient, db: Session
) -> None:
    make_user(db, "ex.employee", password=None, email="ex@example.com")
    assert sso_client.get("/api/auth/me", headers=sso("oid-5", "ex@example.com")).status_code == 200
    db.execute(
        update(User).where(User.username == "ex.employee").values(status=UserStatus.SUSPENDED)
    )
    db.commit()
    response = sso_client.get("/api/auth/me", headers=sso("oid-5", "ex@example.com"))
    assert response.status_code == 403


def test_builtin_accounts_are_never_linked_by_email(sso_client: TestClient, db: Session) -> None:
    db.execute(update(User).where(User.username == "admin").values(email="boss@example.com"))
    db.commit()
    response = sso_client.get("/api/auth/me", headers=sso("oid-evil", "boss@example.com"))
    assert response.status_code == 401
    assert db.scalar(select(ExternalIdentity.id)) is None


def test_without_a_configured_provider_sso_headers_mean_nothing(client: TestClient) -> None:
    me = client.get("/api/auth/me", headers=sso("oid-123", "someone@example.com")).json()
    assert me["is_anonymous"] is True
    assert me["login"]["providers"] == []
    paths = client.get("/api/openapi.json").json()["paths"]
    assert not [p for p in paths if p.startswith("/api/auth/sso")]  # no sign-in routes
