"""Administration shapes: users, passwords, role assignments, roles, organization, audit log,
backups."""

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field, StringConstraints

from taskboard.domain.access import Permission, ScopeKind, UserKind, UserStatus
from taskboard.domain.backups import LIMITS, KeptAs

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._@\\-]{1,99}$"
    ),
]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Password = Annotated[str, StringConstraints(max_length=1000)]
RoleKey = Annotated[
    str, StringConstraints(strip_whitespace=True, pattern=r"^[a-z][a-z0-9_-]{1,49}$")
]
Code = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, min_length=1, max_length=20)
]
# Process codes prefix change keys ("CC" → "CC-31"), so letters and digits only.
ProcessCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{1,10}$")
]
PersonCode = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9]{1,8}$")
]
Color = Annotated[str, StringConstraints(pattern=r"^#[0-9A-Fa-f]{6}$")]
ShortName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
# A light check (something@something.tld); the identity provider is the real authority.
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]


# ---------------------------------------------------------------- users


class AssignmentIn(BaseModel):
    role_id: int
    scope: ScopeKind = ScopeKind.GLOBAL
    scope_id: int | None = None  # the department or section id


class AssignmentOut(BaseModel):
    id: int
    role_id: int
    role_name: str
    scope: ScopeKind
    scope_id: int | None
    scope_label: str  # "Everywhere", "STL", "STL · Quality"


class ExternalIdentityOut(BaseModel):
    provider: str
    subject: str
    last_seen_at: datetime | None


class UserOut(BaseModel):
    id: int
    username: str
    display_name: str
    email: str | None
    person_id: int | None
    status: UserStatus
    kind: UserKind
    is_builtin: bool
    has_password: bool
    must_change_password: bool
    created_at: datetime
    last_login_at: datetime | None
    external_identities: list[ExternalIdentityOut]
    assignments: list[AssignmentOut]


class UserCreate(BaseModel):
    username: Username
    display_name: DisplayName
    email: Email | None = None
    person_id: int | None = None
    # SSO only: no password; status "pending" until the first SSO login links the account.
    sso_only: bool = False
    # Local accounts: leave empty to generate one. Either way it must be changed at first login.
    password: Password | None = None
    assignments: list[AssignmentIn] = []


class UserCreated(BaseModel):
    user: UserOut
    generated_password: str | None  # shown once; never stored in clear


class UserUpdate(BaseModel):
    """Fields sent are changed; `email`/`person_id` may be sent as null to clear them."""

    display_name: DisplayName | None = None
    email: Email | None = None
    person_id: int | None = None
    status: UserStatus | None = None


class PasswordReset(BaseModel):
    password: Password | None = None  # empty: generate one


class PasswordResetOut(BaseModel):
    generated_password: str | None


class ProviderInfo(BaseModel):
    name: str
    display_name: str
    kind: str  # "redirect" (OpenID Connect) or "ambient" (trusted proxy header)


class GroupMappingIn(BaseModel):
    provider: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    group_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)
    ]
    role_id: int
    scope: ScopeKind = ScopeKind.GLOBAL
    scope_id: int | None = None


class GroupMappingOut(BaseModel):
    id: int
    provider: str
    group_name: str
    role_id: int
    role_name: str
    scope: ScopeKind
    scope_id: int | None
    scope_label: str


# ---------------------------------------------------------------- roles


class PermissionInfo(BaseModel):
    value: Permission
    scoped: bool
    description: str


class RoleOut(BaseModel):
    id: int
    key: str
    name: str
    description: str
    is_builtin: bool
    permissions: list[Permission]
    assignment_count: int


class RoleCreate(BaseModel):
    key: RoleKey
    name: ShortName
    description: Annotated[str, StringConstraints(max_length=2000)] = ""
    permissions: list[Permission] = Field(default_factory=list[Permission])


class RoleUpdate(BaseModel):
    name: ShortName | None = None
    description: Annotated[str, StringConstraints(max_length=2000)] | None = None
    permissions: list[Permission] | None = None


# ---------------------------------------------------------------- organization


class DepartmentIn(BaseModel):
    code: Code
    name: ShortName


class DepartmentUpdate(BaseModel):
    code: Code | None = None
    name: ShortName | None = None
    position: int | None = None


class SectionIn(BaseModel):
    department_id: int
    name: ShortName


class SectionUpdate(BaseModel):
    name: ShortName | None = None
    position: int | None = None


class ProcessIn(BaseModel):
    code: ProcessCode
    name: DisplayName
    section_id: int  # the owning section: its department, and who may see and edit the process


class ProcessUpdate(BaseModel):
    """The code is fixed once created (it is part of change keys and links)."""

    name: DisplayName | None = None
    section_id: int | None = None
    position: int | None = None


class PersonAdminOut(BaseModel):
    id: int
    code: str
    name: str
    color: str
    email: str | None
    section_id: int
    department_id: int
    active: bool
    user_id: int | None  # the linked login account, if any


class PersonIn(BaseModel):
    code: PersonCode
    name: DisplayName
    color: Color
    email: Email | None = None
    section_id: int
    active: bool = True


class PersonUpdate(BaseModel):
    """Fields sent are changed; `email` may be sent as null to clear it."""

    code: PersonCode | None = None
    name: DisplayName | None = None
    color: Color | None = None
    email: Email | None = None
    section_id: int | None = None
    active: bool | None = None


# ---------------------------------------------------------------- audit


class AuditEntryOut(BaseModel):
    id: int
    at: datetime
    actor: str | None  # display name; None for the system (startup seeding)
    action: str
    target_type: str | None
    target_id: str | None
    details: dict[str, Any]


# ---------------------------------------------------------------- backups


def _kept(kind: KeptAs) -> Any:
    return Field(ge=LIMITS[kind].low, le=LIMITS[kind].high)


class RetentionIn(BaseModel):
    """How many backups to keep (D-100): the newest ones, and the first of each recent week and
    month that has one."""

    newest: Annotated[int, _kept(KeptAs.NEWEST)]
    weekly: Annotated[int, _kept(KeptAs.WEEKLY)]
    monthly: Annotated[int, _kept(KeptAs.MONTHLY)]


class RetentionOut(BaseModel):
    newest: int
    weekly: int
    monthly: int


class RetentionLimit(BaseModel):
    min: int
    max: int


class BackupOut(BaseModel):
    name: str
    taken_at: datetime
    size: int  # bytes
    kept_as: list[KeptAs]  # empty: the next backup deletes it


class BackupOverview(BaseModel):
    location: str  # TASKBOARD_BACKUP_DIR (a server setting, not changed here)
    problem: str | None  # why the folder cannot be read
    backups: list[BackupOut]  # newest first
    total_size: int
    overdue: bool  # no backup in the last two days
    retention: RetentionOut
    limits: dict[KeptAs, RetentionLimit]
