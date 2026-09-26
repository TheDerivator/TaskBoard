"""Principals loaded from the database: grants, scopes, the anonymous floor, refusals."""

from collections.abc import Iterator

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.models import Role, RolePermission, User
from taskboard.db.session import Database
from taskboard.domain.access import BuiltinRole, Permission, Scope
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)
from taskboard.identity.principal import anonymous_principal, load_grants, principal_for_user
from tests.helpers import make_user, revoke_anonymous_access, section_id


@pytest.fixture
def s(sample_database: Database) -> Iterator[Session]:
    with sample_database.new_session(write=True) as session:
        yield session


def _user(s: Session, username: str) -> User:
    return s.scalars(select(User).where(User.username == username)).one()


def test_anonymous_views_everything_until_an_admin_revokes_it(s: Session) -> None:
    quality = section_id(s, "Quality")
    assert anonymous_principal(s).can(Permission.TASK_VIEW, quality)
    revoke_anonymous_access(s)
    anonymous = anonymous_principal(s)
    assert not anonymous.can(Permission.TASK_VIEW, quality)
    assert anonymous.reach(Permission.TASK_VIEW).nowhere
    with pytest.raises(AuthenticationRequiredError):
        anonymous.require(Permission.TASK_VIEW, quality)


def test_department_editor_edits_only_in_their_department(s: Session) -> None:
    anna = principal_for_user(s, _user(s, "anna.claes"))  # Editor on STL (sample data)
    assert anna.can(Permission.TASK_EDIT, section_id(s, "Quality"))
    assert anna.can(Permission.TASK_EDIT, section_id(s, "Maintenance"))
    assert not anna.can(Permission.TASK_EDIT, section_id(s, "Coatings"))
    assert anna.can(Permission.TASK_VIEW, section_id(s, "Coatings"))  # anonymous floor
    with pytest.raises(PermissionDeniedError):
        anna.require(Permission.TASK_EDIT, section_id(s, "Coatings"))
    reach = anna.reach(Permission.TASK_EDIT)
    assert reach.section_ids == {section_id(s, n) for n in ("Quality", "Process", "Maintenance")}


def test_section_editor(s: Session) -> None:
    user = make_user(
        s, "sofie", roles=[(BuiltinRole.EDITOR, Scope.section(section_id(s, "Coatings")))]
    )
    sofie = principal_for_user(s, user)
    assert sofie.can(Permission.TASK_COMMENT, section_id(s, "Coatings"))
    assert not sofie.can(Permission.TASK_EDIT, section_id(s, "Quality"))
    assert sofie.can_somewhere(Permission.TASK_EDIT)
    assert not sofie.can(Permission.PROJECT_MANAGE)


def test_logged_in_users_never_see_less_than_anonymous(s: Session) -> None:
    nobody = principal_for_user(s, make_user(s, "nobody"))
    assert nobody.can(Permission.TASK_VIEW, section_id(s, "Quality"))
    revoke_anonymous_access(s)
    assert not principal_for_user(s, _user(s, "nobody")).can(Permission.TASK_VIEW)


def test_unknown_sections_are_never_allowed(s: Session) -> None:
    admin = principal_for_user(s, _user(s, "admin"))
    assert not admin.can(Permission.TASK_VIEW, 999_999)


def test_a_pending_password_change_blocks_everything(s: Session) -> None:
    user = make_user(
        s, "new", roles=[(BuiltinRole.ADMIN, Scope.everywhere())], must_change_password=True
    )
    principal = principal_for_user(s, user)
    assert not principal.can(Permission.TASK_VIEW)
    assert principal.reach(Permission.TASK_VIEW).nowhere
    with pytest.raises(PasswordChangeRequiredError):
        principal.require(Permission.TASK_VIEW)


def test_permissions_unknown_to_the_code_are_ignored(s: Session) -> None:
    viewer = s.scalars(select(Role).where(Role.key == "viewer")).one()
    viewer.permissions.append(RolePermission(permission="removed.permission"))
    s.flush()
    anonymous = _user(s, "anonymous")
    assert {g.permission for g in load_grants(s, anonymous.id)} == {Permission.TASK_VIEW}
