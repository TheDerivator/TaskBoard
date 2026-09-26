"""Built-in roles and users: created once, idempotent, respectful of admin changes."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taskboard.db.models import AppLock, Role, RoleAssignment, RolePermission, User
from taskboard.db.session import TASK_RANKING_LOCK, Database, acquire_lock
from taskboard.domain.access import BuiltinRole, Permission, ScopeKind, UserKind
from taskboard.identity.passwords import verify_password
from taskboard.services.seed import seed_builtins
from tests.conftest import TEST_ADMIN_PASSWORD, sqlite_url


def _user(session: Session, username: str) -> User:
    return session.scalars(select(User).where(User.username == username)).one()


def _role_keys(user: User) -> set[tuple[str, str]]:
    return {(a.role.key, a.scope_key) for a in user.assignments}


def test_builtin_roles_have_their_permissions(session: Session) -> None:
    for builtin in BuiltinRole:
        role = session.scalars(select(Role).where(Role.key == builtin.value)).one()
        assert role.is_builtin
        assert {rp.permission for rp in role.permissions} == set(builtin.permissions)
    admin_role = session.scalars(select(Role).where(Role.key == "admin")).one()
    assert {rp.permission for rp in admin_role.permissions} == set(Permission)


def test_anonymous_views_everything_by_default(session: Session) -> None:
    anonymous = _user(session, "anonymous")
    assert anonymous.kind is UserKind.ANONYMOUS
    assert anonymous.password_hash is None
    assert _role_keys(anonymous) == {("viewer", ScopeKind.GLOBAL.value)}


def test_admin_is_administrator_everywhere_with_the_configured_password(session: Session) -> None:
    admin = _user(session, "admin")
    assert admin.is_builtin
    assert _role_keys(admin) == {("admin", "global")}
    assert verify_password(admin.password_hash, TEST_ADMIN_PASSWORD)
    assert not admin.must_change_password


def test_seeding_again_changes_nothing(session: Session) -> None:
    def counts() -> tuple[int, ...]:
        return tuple(
            session.scalar(select(func.count()).select_from(model)) or 0
            for model in (User, Role, RolePermission, RoleAssignment, AppLock)
        )

    before = counts()
    report = seed_builtins(session, initial_admin_password="something-else")
    assert report.created == []
    assert counts() == before


def test_seed_resyncs_builtin_role_permissions(session: Session) -> None:
    viewer = session.scalars(select(Role).where(Role.key == "viewer")).one()
    viewer.permissions.append(RolePermission(permission=Permission.USERS_MANAGE.value))
    session.flush()
    seed_builtins(session)
    assert {rp.permission for rp in viewer.permissions} == {Permission.TASK_VIEW.value}


def test_seed_does_not_restore_anonymous_rights_an_admin_removed(session: Session) -> None:
    anonymous = _user(session, "anonymous")
    anonymous.assignments.clear()
    session.flush()
    seed_builtins(session)
    assert anonymous.assignments == []


def test_generated_admin_password_must_be_changed(tmp_path_factory: pytest.TempPathFactory) -> None:
    from taskboard.services.setup import prepare_database

    database = Database(sqlite_url(tmp_path_factory.mktemp("gen") / "db.sqlite3"))
    report = prepare_database(database, initial_admin_password=None)
    assert report.generated_admin_password
    with database.session() as s:
        admin = _user(s, "admin")
        assert admin.must_change_password
        assert verify_password(admin.password_hash, report.generated_admin_password)
    database.dispose()


def test_lock_rows_exist_and_can_be_taken(session: Session) -> None:
    acquire_lock(session, TASK_RANKING_LOCK)
    acquire_lock(session, TASK_RANKING_LOCK)
    lock = session.get(AppLock, TASK_RANKING_LOCK)
    assert lock and lock.counter == 2
