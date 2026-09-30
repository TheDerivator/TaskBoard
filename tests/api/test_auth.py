"""Password login, sessions, logout, throttling, CSRF, suspension and password changes over HTTP."""

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from taskboard.config import Settings
from taskboard.db.base import utcnow
from taskboard.db.models import User, UserSession
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.sessions import SESSION_COOKIE
from taskboard.web import create_app
from taskboard.web.csrf import CSRF_HEADER
from tests.conftest import TEST_ADMIN_PASSWORD, start_client
from tests.helpers import PASSWORD, login, make_user


@pytest.fixture
def db(database: Database) -> Iterator[Session]:
    with database.new_session(write=True) as session:
        yield session


def test_visitors_are_anonymous_and_can_view_by_default(client: TestClient) -> None:
    me = client.get("/api/auth/me").json()
    assert me["is_anonymous"] is True
    assert me["permissions"]["task.view"] == {"everywhere": True, "section_ids": []}
    assert me["permissions"]["task.edit"] == {"everywhere": False, "section_ids": []}
    assert me["login"] == {"password": True, "providers": [], "windows": None}


def test_admin_logs_in_with_a_session_cookie(client: TestClient) -> None:
    response = login(client, "admin", TEST_ADMIN_PASSWORD)
    assert response.status_code == 200
    assert response.json()["username"] == "admin"
    cookie = response.headers["set-cookie"]
    assert (
        f"{SESSION_COOKIE}=" in cookie and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    )
    me = client.get("/api/auth/me").json()
    assert me["is_anonymous"] is False and me["signed_in_by"] is None  # logging out is possible
    assert me["permissions"]["users.manage"]["everywhere"] is True


def test_usernames_are_case_insensitive(client: TestClient) -> None:
    assert login(client, "  ADMIN ", TEST_ADMIN_PASSWORD).status_code == 200


@pytest.mark.parametrize(("username", "password"), [("admin", "wrong"), ("nobody", "wrong")])
def test_failed_login_does_not_reveal_whether_the_user_exists(
    client: TestClient, username: str, password: str
) -> None:
    response = login(client, username, password)
    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_credentials",
        "message": "unknown username or wrong password",
    }


def test_logout_ends_the_session(client: TestClient, db: Session) -> None:
    login(client, "admin", TEST_ADMIN_PASSWORD)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    assert db.scalar(select(UserSession.id)) is None


def test_expired_sessions_are_ignored(client: TestClient, db: Session) -> None:
    login(client, "admin", TEST_ADMIN_PASSWORD)
    db.execute(update(UserSession).values(expires_at=utcnow() - timedelta(minutes=1)))
    db.commit()
    assert client.get("/api/auth/me").json()["is_anonymous"] is True


def test_repeated_failures_are_throttled_even_with_the_right_password(client: TestClient) -> None:
    for _ in range(5):
        assert login(client, "admin", "wrong").status_code == 401
    response = login(client, "admin", TEST_ADMIN_PASSWORD)
    assert response.status_code == 429
    assert response.json()["error"] == "too_many_attempts"
    assert int(response.headers["Retry-After"]) > 0


def test_a_successful_login_resets_the_account_failure_count(client: TestClient) -> None:
    for _ in range(4):
        login(client, "admin", "wrong")
    assert login(client, "admin", TEST_ADMIN_PASSWORD).status_code == 200
    for _ in range(4):
        login(client, "admin", "wrong")
    assert login(client, "admin", TEST_ADMIN_PASSWORD).status_code == 200


def test_state_changes_without_the_csrf_header_are_refused(client: TestClient) -> None:
    for header in ("", "forged"):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
            headers={CSRF_HEADER: header},
        )
        assert response.status_code == 403
        assert response.json()["error"] == "csrf_failed"


def test_suspension_takes_effect_on_the_next_request(client: TestClient, db: Session) -> None:
    make_user(db, "sam", roles=[(BuiltinRole.EDITOR, Scope.everywhere())])
    login(client, "sam")
    assert client.get("/api/auth/me").json()["username"] == "sam"
    db.execute(update(User).where(User.username == "sam").values(status=UserStatus.SUSPENDED))
    db.commit()
    assert client.get("/api/auth/me").json()["is_anonymous"] is True
    assert login(client, "sam").status_code == 401


@pytest.mark.parametrize("status", [UserStatus.SUSPENDED, UserStatus.PENDING])
def test_inactive_accounts_cannot_log_in(
    client: TestClient, db: Session, status: UserStatus
) -> None:
    make_user(db, "pat", status=status)
    assert login(client, "pat").status_code == 401


def test_the_anonymous_account_cannot_log_in(client: TestClient) -> None:
    assert login(client, "anonymous", "").status_code == 422  # empty password: invalid request
    assert login(client, "anonymous", "anything").status_code == 401


def test_changing_the_password(client: TestClient, db: Session) -> None:
    make_user(db, "kim", must_change_password=True)
    assert login(client, "kim").json()["must_change_password"] is True
    change = {"current_password": PASSWORD, "new_password": "a much better password"}
    assert client.post("/api/auth/password", json=change).status_code == 204
    assert client.get("/api/auth/me").json()["must_change_password"] is False
    client.post("/api/auth/logout")
    assert login(client, "kim").status_code == 401
    assert login(client, "kim", "a much better password").status_code == 200


def test_password_change_rules(client: TestClient, db: Session) -> None:
    make_user(db, "lee")
    login(client, "lee")
    wrong = client.post(
        "/api/auth/password", json={"current_password": "nope", "new_password": "long enough pw"}
    )
    assert wrong.status_code == 401
    short = client.post(
        "/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}
    )
    assert short.status_code == 422
    assert "at least 10 characters" in short.json()["message"]


def test_changing_the_password_logs_out_other_sessions(settings: Settings, db: Session) -> None:
    make_user(db, "max")
    app = create_app(settings)
    laptop, phone = start_client(app), start_client(app)
    laptop_client, phone_client = next(laptop), next(phone)
    login(laptop_client, "max")
    login(phone_client, "max")
    change = {"current_password": PASSWORD, "new_password": "another good password"}
    assert laptop_client.post("/api/auth/password", json=change).status_code == 204
    assert laptop_client.get("/api/auth/me").json()["username"] == "max"
    assert phone_client.get("/api/auth/me").json()["is_anonymous"] is True
    for generator in (laptop, phone):
        generator.close()


def test_the_first_response_hands_out_a_csrf_cookie(settings: Settings) -> None:
    with TestClient(create_app(settings)) as fresh:
        response = fresh.get("/api/health")
        assert "taskboard_csrf=" in response.headers["set-cookie"]
        assert "samesite=lax" in response.headers["set-cookie"].lower()
        assert fresh.get("/api/auth/me").status_code == 200  # reads need no header


def test_cookies_are_secure_over_https(settings: Settings) -> None:
    with TestClient(create_app(settings), base_url="https://board.example.com") as https:
        https.get("/api/health")
        https.headers[CSRF_HEADER] = https.cookies["taskboard_csrf"]
        response = login(https, "admin", TEST_ADMIN_PASSWORD)
        assert response.status_code == 200
        assert "secure" in response.headers["set-cookie"].lower()
