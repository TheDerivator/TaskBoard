"""Test helpers: create users with given roles, log in through the API."""

from collections.abc import Sequence

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.models import Role, RoleAssignment, Section, User
from taskboard.domain.access import BuiltinRole, Scope, UserStatus
from taskboard.identity.passwords import hash_password

PASSWORD = "correct horse battery"


def make_user(
    session: Session,
    username: str,
    *,
    password: str | None = PASSWORD,
    roles: Sequence[tuple[BuiltinRole, Scope]] = (),
    status: UserStatus = UserStatus.ACTIVE,
    email: str | None = None,
    must_change_password: bool = False,
    display_name: str | None = None,
) -> User:
    """Create and commit a user with the given (role, scope) assignments."""
    user = User(
        username=username,
        display_name=display_name or username.title(),
        password_hash=hash_password(password) if password else None,
        status=status,
        email=email,
        must_change_password=must_change_password,
    )
    for builtin, scope in roles:
        assignment = RoleAssignment(
            role=session.scalars(select(Role).where(Role.key == builtin.value)).one()
        )
        assignment.scope = scope
        user.assignments.append(assignment)
    session.add(user)
    session.commit()
    return user


def section_id(session: Session, name: str) -> int:
    return session.scalars(select(Section.id).where(Section.name == name)).one()


def login(client: TestClient, username: str, password: str = PASSWORD) -> Response:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def revoke_anonymous_access(session: Session) -> None:
    anonymous = session.scalars(select(User).where(User.username == "anonymous")).one()
    anonymous.assignments.clear()
    session.commit()
