"""Built-in data that must always exist: lock rows, built-in roles, the admin and anonymous users,
and the built-in box kinds and link types of process maps.

`seed_builtins` is idempotent and runs at every startup. It creates what is missing and re-syncs
built-in role permissions from code, but never undoes an administrator's choices (for example, it
does not give the anonymous user its view rights back once an admin removed them).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.db.models import (
    AppLock,
    BoxKind,
    LinkType,
    Role,
    RoleAssignment,
    RolePermission,
    User,
)
from taskboard.db.session import LOCK_NAMES
from taskboard.domain.access import (
    ADMIN_USERNAME,
    ANONYMOUS_USERNAME,
    BuiltinRole,
    Scope,
    UserKind,
    UserStatus,
)
from taskboard.domain.knowledge import BUILTIN_KINDS, BUILTIN_LINK_TYPES
from taskboard.identity.passwords import generate_password, hash_password
from taskboard.services import audit


@dataclass
class SeedReport:
    """What `seed_builtins` changed. A generated admin password must be shown to the operator."""

    created: list[str] = field(default_factory=list[str])
    generated_admin_password: str | None = None


def seed_builtins(session: Session, *, initial_admin_password: str | None = None) -> SeedReport:
    report = SeedReport()
    _ensure_locks(session, report)
    roles = _sync_builtin_roles(session, report)
    _ensure_anonymous(session, roles, report)
    _ensure_admin(session, roles, initial_admin_password, report)
    _ensure_map_settings(session, report)
    session.flush()
    return report


def _ensure_map_settings(session: Session, report: SeedReport) -> None:
    """Create missing built-in kinds and link types. An administrator may rename or restyle them
    (Kinds & link types settings), so existing ones are left as they are."""
    kinds = set(session.scalars(select(BoxKind.key)))
    for position, kind in enumerate(BUILTIN_KINDS):
        if kind.key not in kinds:
            session.add(
                BoxKind(
                    key=kind.key,
                    name=kind.name,
                    description=kind.description,
                    role=kind.role,
                    style=kind.style,
                    has_facts=kind.has_facts,
                    has_main_url=kind.has_main_url,
                    builtin=True,
                    position=position,
                    field_schema=list(kind.field_schema),
                )
            )
            report.created.append(f"box kind {kind.key}")
    link_types = set(session.scalars(select(LinkType.key)))
    for position, link_type in enumerate(BUILTIN_LINK_TYPES):
        if link_type.key not in link_types:
            session.add(
                LinkType(
                    key=link_type.key,
                    forward_name=link_type.forward_name,
                    backward_name=link_type.backward_name,
                    description=link_type.description,
                    role=link_type.role,
                    builtin=True,
                    position=position,
                    field_schema=[],
                )
            )
            report.created.append(f"link type {link_type.key}")


def _ensure_locks(session: Session, report: SeedReport) -> None:
    existing = set(session.scalars(select(AppLock.name)))
    for name in LOCK_NAMES:
        if name not in existing:
            session.add(AppLock(name=name))
            report.created.append(f"lock {name}")


def _sync_builtin_roles(session: Session, report: SeedReport) -> dict[BuiltinRole, Role]:
    roles: dict[BuiltinRole, Role] = {}
    for builtin in BuiltinRole:
        role = session.scalar(select(Role).where(Role.key == builtin.value))
        if role is None:
            role = Role(key=builtin.value, name=builtin.label, is_builtin=True)
            session.add(role)
            report.created.append(f"role {builtin.value}")
        wanted = {p.value for p in builtin.permissions}
        role.permissions = [rp for rp in role.permissions if rp.permission in wanted]
        have = {rp.permission for rp in role.permissions}
        role.permissions.extend(RolePermission(permission=p) for p in sorted(wanted - have))
        roles[builtin] = role
    return roles


def _grant(user: User, role: Role, scope: Scope) -> None:
    assignment = RoleAssignment(role=role)
    assignment.scope = scope
    user.assignments.append(assignment)


def _ensure_anonymous(session: Session, roles: dict[BuiltinRole, Role], report: SeedReport) -> None:
    if session.scalar(select(User).where(User.username == ANONYMOUS_USERNAME)):
        return
    user = User(
        username=ANONYMOUS_USERNAME,
        display_name="Anonymous visitor",
        kind=UserKind.ANONYMOUS,
        status=UserStatus.ACTIVE,
        is_builtin=True,
    )
    _grant(user, roles[BuiltinRole.VIEWER], Scope.everywhere())  # default: view everything
    session.add(user)
    session.flush()
    audit.record(session, "user.created", actor_user_id=None, target_type="user", target_id=user.id)
    report.created.append("user anonymous")


def _ensure_admin(
    session: Session,
    roles: dict[BuiltinRole, Role],
    initial_password: str | None,
    report: SeedReport,
) -> None:
    if session.scalar(select(User).where(User.username == ADMIN_USERNAME)):
        return
    password = initial_password or generate_password()
    user = User(
        username=ADMIN_USERNAME,
        display_name="Administrator",
        password_hash=hash_password(password),
        must_change_password=initial_password is None,
        is_builtin=True,
    )
    _grant(user, roles[BuiltinRole.ADMIN], Scope.everywhere())
    session.add(user)
    session.flush()
    audit.record(session, "user.created", actor_user_id=None, target_type="user", target_id=user.id)
    report.created.append("user admin")
    if initial_password is None:
        report.generated_admin_password = password
