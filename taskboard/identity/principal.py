"""The principal: who is making a request and what they may do (loaded once per request).

Services receive a Principal and call `require(...)` before acting, and `reach(...)` to filter
lists. The anonymous visitor is a principal too (the built-in `anonymous` user and its grants).
"""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from taskboard.db.models import (
    ExternalIdentity,
    GroupRoleMapping,
    Role,
    RoleAssignment,
    RolePermission,
    Section,
    User,
)
from taskboard.domain.access import (
    ANONYMOUS_USERNAME,
    Grant,
    GrantSet,
    Permission,
    Reach,
    SectionRef,
    UserKind,
)
from taskboard.domain.errors import (
    AuthenticationRequiredError,
    PasswordChangeRequiredError,
    PermissionDeniedError,
)


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    username: str
    display_name: str
    is_anonymous: bool
    person_id: int | None
    must_change_password: bool
    grants: GrantSet
    sections: Mapping[int, SectionRef]  # every organizational section, to resolve scopes
    # Set when a trusted proxy identifies the user on every request (there is no logging out).
    ambient_provider: str | None = None

    def can(self, permission: Permission, section_id: int | None = None) -> bool:
        if self.must_change_password:
            return False
        section = self.sections.get(section_id) if section_id is not None else None
        if section_id is not None and section is None:
            return False
        return self.grants.allows(permission, section)

    def require(self, permission: Permission, section_id: int | None = None) -> None:
        """Raise unless allowed: 401 for visitors who should log in, 403 otherwise."""
        if self.must_change_password:
            raise PasswordChangeRequiredError("set a new password first")
        if self.can(permission, section_id):
            return
        if self.is_anonymous:
            raise AuthenticationRequiredError("log in to do this")
        raise PermissionDeniedError(f"missing permission {permission.value}")

    def reach(self, permission: Permission) -> Reach:
        """Where `permission` applies, with department grants resolved into sections."""
        if self.must_change_password:
            return Reach(everywhere=False)
        return self.grants.reach(permission, self.sections.values())

    def can_somewhere(self, permission: Permission) -> bool:
        return not self.must_change_password and self.grants.allows_somewhere(permission)


def load_grants(session: Session, user_id: int) -> GrantSet:
    rows = session.execute(
        select(RolePermission.permission, RoleAssignment)
        .join(Role, Role.id == RolePermission.role_id)
        .join(RoleAssignment, RoleAssignment.role_id == Role.id)
        .where(RoleAssignment.user_id == user_id)
    ).all()
    known = {p.value for p in Permission}
    return GrantSet(
        Grant(Permission(permission), assignment.scope)
        for permission, assignment in rows
        if permission in known  # tolerate permissions removed from code but still in the DB
    )


def load_group_grants(session: Session, user_id: int) -> list[Grant]:
    """Grants from group → role mappings, for the groups the user's identities last reported."""
    reported = {
        (provider, group)
        for provider, groups in session.execute(
            select(ExternalIdentity.provider, ExternalIdentity.groups).where(
                ExternalIdentity.user_id == user_id
            )
        )
        for group in groups or []
    }
    if not reported:
        return []
    known = {p.value for p in Permission}
    mappings = session.scalars(
        select(GroupRoleMapping)
        .options(selectinload(GroupRoleMapping.role).selectinload(Role.permissions))
        .where(GroupRoleMapping.provider.in_({provider for provider, _ in reported}))
    )
    return [
        Grant(Permission(rp.permission), mapping.scope)
        for mapping in mappings
        if (mapping.provider, mapping.group_name) in reported
        for rp in mapping.role.permissions
        if rp.permission in known
    ]


def load_sections(session: Session) -> dict[int, SectionRef]:
    return {
        section_id: SectionRef(section_id, department_id)
        for section_id, department_id in session.execute(select(Section.id, Section.department_id))
    }


def principal_for_user(session: Session, user: User) -> Principal:
    """Own roles, roles from identity-provider groups, and at least the anonymous visitor's
    rights (logging in never shows less)."""
    is_anonymous = user.kind is UserKind.ANONYMOUS
    grants = load_grants(session, user.id)
    if not is_anonymous:
        grants = GrantSet([*grants, *load_group_grants(session, user.id)])
        anonymous_id = session.scalar(select(User.id).where(User.username == ANONYMOUS_USERNAME))
        if anonymous_id is not None:
            grants = GrantSet([*grants, *load_grants(session, anonymous_id)])
    return Principal(
        user_id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_anonymous=is_anonymous,
        person_id=user.person_id,
        must_change_password=user.must_change_password,
        grants=grants,
        sections=load_sections(session),
    )


def anonymous_principal(session: Session) -> Principal:
    user = session.scalars(select(User).where(User.username == ANONYMOUS_USERNAME)).one()
    return principal_for_user(session, user)
