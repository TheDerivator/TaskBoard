"""Access-control vocabulary: permissions, built-in roles, scopes and account states.

Pure data and pure decisions. The database-backed parts (loading a user's assignments, building
query filters) live in `taskboard.identity`.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    """Everything that can be granted. Scoped permissions apply per organizational section:
    a task's section, or the owning section of a process (its changes and its map)."""

    TASK_VIEW = "task.view"
    TASK_EDIT = "task.edit"
    TASK_COMMENT = "task.comment"
    TASK_DELETE = "task.delete"  # destructive (archiving exists); only Administrators by default
    CHANGE_VIEW = "change.view"
    CHANGE_EDIT = "change.edit"
    CHANGE_COMMENT = "change.comment"
    CHANGE_DELETE = "change.delete"  # like task.delete: only Administrators by default
    KNOWLEDGE_VIEW = "knowledge.view"
    KNOWLEDGE_EDIT = "knowledge.edit"
    KNOWLEDGE_RELEASE = "knowledge.release"
    KNOWLEDGE_CONFIGURE = "knowledge.configure"  # box kinds and link types, shared by all maps
    PROJECT_MANAGE = "project.manage"
    PEOPLE_MANAGE = "people.manage"
    USERS_MANAGE = "users.manage"

    @property
    def is_scoped(self) -> bool:
        return self in SCOPED_PERMISSIONS


PERMISSION_DESCRIPTIONS: dict[Permission, str] = {
    Permission.TASK_VIEW: "See tasks, their conversation and attachments",
    Permission.TASK_EDIT: "Create and edit tasks, reorder them, place them in projects",
    Permission.TASK_COMMENT: "Write posts and attach images in the conversation",
    Permission.TASK_DELETE: "Delete tasks for good (archiving is the usual way)",
    Permission.CHANGE_VIEW: "See process changes, their periods and conversation",
    Permission.CHANGE_EDIT: "Create and edit process changes, post periods, link them to the map",
    Permission.CHANGE_COMMENT: "Write comments and attach images in a change's conversation",
    Permission.CHANGE_DELETE: "Delete process changes for good",
    Permission.KNOWLEDGE_VIEW: "See process maps, FMEA and control plans, and their versions",
    Permission.KNOWLEDGE_EDIT: "Edit process maps: boxes, links, controls and defects",
    Permission.KNOWLEDGE_RELEASE: "Release a new FMEA and control plan version",
    Permission.KNOWLEDGE_CONFIGURE: "Configure the box kinds and link types of all process maps",
    Permission.PROJECT_MANAGE: "Create projects and edit their sections",
    Permission.PEOPLE_MANAGE: "Manage departments, sections, processes and people",
    Permission.USERS_MANAGE: "Manage accounts, roles and access rights; read the audit log",
}

SCOPED_PERMISSIONS = frozenset(
    {
        Permission.TASK_VIEW,
        Permission.TASK_EDIT,
        Permission.TASK_COMMENT,
        Permission.TASK_DELETE,
        Permission.CHANGE_VIEW,
        Permission.CHANGE_EDIT,
        Permission.CHANGE_COMMENT,
        Permission.CHANGE_DELETE,
        Permission.KNOWLEDGE_VIEW,
        Permission.KNOWLEDGE_EDIT,
        Permission.KNOWLEDGE_RELEASE,
    }
)

# Seeing any of these somewhere is what gives access to the board's reference data (departments,
# people, processes).
VIEW_PERMISSIONS = (Permission.TASK_VIEW, Permission.CHANGE_VIEW, Permission.KNOWLEDGE_VIEW)


class BuiltinRole(StrEnum):
    """Roles that always exist. Their permissions are synced from code at startup."""

    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"

    @property
    def label(self) -> str:
        return {"viewer": "Viewer", "editor": "Editor", "admin": "Administrator"}[self.value]

    @property
    def permissions(self) -> frozenset[Permission]:
        return BUILTIN_ROLE_PERMISSIONS[self]


_VIEWER = frozenset(VIEW_PERMISSIONS)

BUILTIN_ROLE_PERMISSIONS: dict[BuiltinRole, frozenset[Permission]] = {
    BuiltinRole.VIEWER: _VIEWER,
    BuiltinRole.EDITOR: _VIEWER
    | {
        Permission.TASK_EDIT,
        Permission.TASK_COMMENT,
        Permission.CHANGE_EDIT,
        Permission.CHANGE_COMMENT,
        Permission.KNOWLEDGE_EDIT,
        Permission.KNOWLEDGE_RELEASE,
    },
    BuiltinRole.ADMIN: frozenset(Permission),
}


class ScopeKind(StrEnum):
    GLOBAL = "global"
    DEPARTMENT = "department"
    SECTION = "section"


@dataclass(frozen=True, slots=True)
class Scope:
    """Where a role assignment applies: everywhere, one department, or one section."""

    kind: ScopeKind
    id: int | None = None

    def __post_init__(self) -> None:
        if (self.kind is ScopeKind.GLOBAL) != (self.id is None):
            raise ValueError("a global scope has no id; department and section scopes need one")

    @property
    def key(self) -> str:
        """Stable text form (`global`, `department:3`, `section:7`), unique per assignment."""
        return self.kind.value if self.id is None else f"{self.kind.value}:{self.id}"

    @classmethod
    def everywhere(cls) -> Scope:
        return cls(ScopeKind.GLOBAL)

    @classmethod
    def department(cls, department_id: int) -> Scope:
        return cls(ScopeKind.DEPARTMENT, department_id)

    @classmethod
    def section(cls, section_id: int) -> Scope:
        return cls(ScopeKind.SECTION, section_id)


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"  # pre-provisioned; becomes active at first external login


class UserKind(StrEnum):
    REGULAR = "regular"
    ANONYMOUS = "anonymous"  # the built-in principal for visitors who are not logged in


ADMIN_USERNAME = "admin"
ANONYMOUS_USERNAME = "anonymous"


# ---------------------------------------------------------------- decisions


@dataclass(frozen=True, slots=True)
class SectionRef:
    """Where a task lives in the organization: its section and that section's department."""

    id: int
    department_id: int


@dataclass(frozen=True, slots=True)
class Grant:
    """One permission at one scope (a role assignment expands into several grants)."""

    permission: Permission
    scope: Scope


@dataclass(frozen=True, slots=True)
class Reach:
    """Where a permission applies: everywhere, or in a set of sections."""

    everywhere: bool
    section_ids: frozenset[int] = frozenset()

    def includes(self, section_id: int) -> bool:
        return self.everywhere or section_id in self.section_ids

    @property
    def nowhere(self) -> bool:
        return not self.everywhere and not self.section_ids


class GrantSet:
    """Everything a principal is allowed, and the decisions derived from it.

    Rules:
    - A scoped permission (task.*) applies to a section if granted globally, for that section's
      department, or for that section itself.
    - An unscoped permission (project/people/users.manage) only counts when granted globally.
    """

    def __init__(self, grants: Iterable[Grant] = ()) -> None:
        self._grants = frozenset(grants)

    def __iter__(self) -> Iterator[Grant]:
        return iter(self._grants)

    def allows(self, permission: Permission, section: SectionRef | None = None) -> bool:
        """For scoped permissions, `section=None` asks "allowed in every section?"."""
        for grant in self._grants:
            if grant.permission is not permission:
                continue
            scope = grant.scope
            if scope.kind is ScopeKind.GLOBAL:
                return True
            if section is None or not permission.is_scoped:
                continue
            if scope.kind is ScopeKind.DEPARTMENT and scope.id == section.department_id:
                return True
            if scope.kind is ScopeKind.SECTION and scope.id == section.id:
                return True
        return False

    def allows_somewhere(self, permission: Permission) -> bool:
        """For showing controls: e.g. 'New task' needs edit rights in at least one section."""
        return any(
            g.permission is permission
            and (permission.is_scoped or g.scope.kind is ScopeKind.GLOBAL)
            for g in self._grants
        )

    def reach(self, permission: Permission, sections: Iterable[SectionRef]) -> Reach:
        """Resolve department grants into concrete sections (e.g. for filtering task lists)."""
        if self.allows(permission):
            return Reach(everywhere=True)
        if not permission.is_scoped:
            return Reach(everywhere=False)
        return Reach(
            everywhere=False,
            section_ids=frozenset(s.id for s in sections if self.allows(permission, s)),
        )
