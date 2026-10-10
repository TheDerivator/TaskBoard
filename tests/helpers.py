"""Test helpers: users with given roles (built-in or custom), logging in, revision checks, backup
files."""

from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    Box,
    BoxLink,
    Control,
    Revision,
    Role,
    RoleAssignment,
    RolePermission,
    Section,
    User,
)
from taskboard.domain.access import BuiltinRole, Permission, Scope, UserStatus
from taskboard.identity.passwords import hash_password
from taskboard.services.knowledge import box_content, control_content, link_content

PASSWORD = "correct horse battery"


def make_user(
    session: Session,
    username: str,
    *,
    password: str | None = PASSWORD,
    roles: Sequence[tuple[BuiltinRole | str, Scope]] = (),  # a built-in role or a role key
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
    for role_key, scope in roles:
        assignment = RoleAssignment(
            role=session.scalars(select(Role).where(Role.key == str(role_key))).one()
        )
        assignment.scope = scope
        user.assignments.append(assignment)
    session.add(user)
    session.commit()
    return user


def make_role(session: Session, key: str, permissions: Sequence[Permission]) -> Role:
    """Create and commit a custom role holding exactly `permissions`."""
    role = Role(
        key=key,
        name=key.title(),
        permissions=[RolePermission(permission=p.value) for p in permissions],
    )
    session.add(role)
    session.commit()
    return role


def section_id(session: Session, name: str) -> int:
    return session.scalars(select(Section.id).where(Section.name == name)).one()


def login(client: TestClient, username: str, password: str = PASSWORD) -> Response:
    return client.post("/api/auth/login", json={"username": username, "password": password})


def revoke_anonymous_access(session: Session) -> None:
    anonymous = session.scalars(select(User).where(User.username == "anonymous")).one()
    anonymous.assignments.clear()
    session.commit()


def assert_revisions_match_rows(session: Session) -> None:
    """Every box, link and control's latest revision holds exactly its current content (the
    revisions never drift from the rows; releases and history rely on that)."""
    latest: dict[tuple[str, int], Revision] = {}
    for revision in session.scalars(select(Revision).order_by(Revision.rev)):
        latest[revision.object_type.value, revision.object_id] = revision
    current = [
        *(("box", b.id, b.rev, box_content(session, b)) for b in session.scalars(select(Box))),
        *(
            ("link", lk.id, lk.rev, link_content(session, lk))
            for lk in session.scalars(select(BoxLink))
        ),
        *(
            ("control", c.id, c.rev, control_content(session, c))
            for c in session.scalars(select(Control))
        ),
    ]
    for object_type, object_id, rev, content in current:
        revision = latest.get((object_type, object_id))
        assert revision is not None, f"{object_type} {object_id} has no revision"
        assert not revision.deleted and revision.rev == rev, (object_type, object_id)
        assert revision.content == content, (object_type, object_id)
    alive = {(t, i) for t, i, _, _ in current}
    for (object_type, object_id), revision in latest.items():
        if (object_type, object_id) not in alive:
            assert revision.deleted, (
                f"{object_type} {object_id} is gone without a deletion revision"
            )


def fake_backups(folder: Path, *days: str) -> list[str]:
    """Backup files as `python -m taskboard backup` names them, taken at noon UTC on these days
    (the same day in any server time zone); the n-th is n kB. Keeping looks at names only."""
    folder.mkdir(parents=True, exist_ok=True)
    names = [f"taskboard-backup-{day.replace('-', '')}-120000.zip" for day in days]
    for size, name in enumerate(names, start=1):
        (folder / name).write_bytes(b"z" * 1000 * size)
    return names
