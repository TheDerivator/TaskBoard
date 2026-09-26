"""Accounts and access control: users, external identities, roles, assignments, sessions, audit."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    Unicode,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from taskboard.db.base import (
    Base,
    Email,
    Name,
    ShortText,
    Text,
    UTCDateTime,
    normalize_email,
    normalize_username,
    str_enum,
    utcnow,
)
from taskboard.db.models.org import Department, Section
from taskboard.db.models.people import Person
from taskboard.domain.access import Scope, ScopeKind, UserKind, UserStatus


class User(Base):
    """A login account. Built-in accounts (admin, anonymous) cannot be deleted."""

    __tablename__ = "users"
    __table_args__ = (
        # Filtered unique indexes: MS SQL's UNIQUE would allow only one NULL.
        Index(
            "uq_users_email",
            "email",
            unique=True,
            sqlite_where=text("email IS NOT NULL"),
            mssql_where=text("email IS NOT NULL"),
        ),
        Index(
            "uq_users_person_id",
            "person_id",
            unique=True,
            sqlite_where=text("person_id IS NOT NULL"),
            mssql_where=text("person_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(ShortText, unique=True)  # stored lowercase
    display_name: Mapped[str] = mapped_column(Name)
    email: Mapped[str | None] = mapped_column(Email)  # stored lowercase; SSO matches on it
    person_id: Mapped[int | None] = mapped_column(ForeignKey("people.id"))
    password_hash: Mapped[str | None] = mapped_column(Unicode(255))  # None: no local login
    must_change_password: Mapped[bool] = mapped_column(default=False)
    status: Mapped[UserStatus] = mapped_column(str_enum(UserStatus), default=UserStatus.ACTIVE)
    kind: Mapped[UserKind] = mapped_column(str_enum(UserKind), default=UserKind.REGULAR)
    is_builtin: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    person: Mapped[Person | None] = relationship()
    assignments: Mapped[list[RoleAssignment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    external_identities: Mapped[list[ExternalIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @validates("username")
    def _normalize_username(self, _key: str, value: str) -> str:
        return normalize_username(value)

    @validates("email")
    def _normalize_email(self, _key: str, value: str | None) -> str | None:
        return normalize_email(value)


class ExternalIdentity(Base):
    """Links an identity at an external provider (e.g. Entra ID `sub`) to a user."""

    __tablename__ = "external_identities"
    __table_args__ = (UniqueConstraint("provider", "subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    subject: Mapped[str] = mapped_column(Unicode(255))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # The provider's groups at the last sign-in; group mappings grant roles from these.
    groups: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")

    user: Mapped[User] = relationship(back_populates="external_identities")


class GroupRoleMapping(Base):
    """Everyone in an identity-provider group holds a role at a scope (while they are in it).

    `scope_key` mirrors the scope as text so uniqueness works the same on every backend.
    """

    __tablename__ = "group_role_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "group_name", "role_id", "scope_key"),
        CheckConstraint("department_id IS NULL OR section_id IS NULL", name="one_scope_only"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    group_name: Mapped[str] = mapped_column(
        Unicode(255)
    )  # as the provider sends it (Entra: object id)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"))
    scope_key: Mapped[str] = mapped_column(Unicode(40))

    role: Mapped[Role] = relationship()

    @property
    def scope(self) -> Scope:
        if self.section_id is not None:
            return Scope(ScopeKind.SECTION, self.section_id)
        if self.department_id is not None:
            return Scope(ScopeKind.DEPARTMENT, self.department_id)
        return Scope(ScopeKind.GLOBAL)

    @scope.setter
    def scope(self, scope: Scope) -> None:
        self.department_id = scope.id if scope.kind is ScopeKind.DEPARTMENT else None
        self.section_id = scope.id if scope.kind is ScopeKind.SECTION else None
        self.scope_key = scope.key


class SsoRequest(Base):
    """A sign-in in progress at an external provider (state, nonce, PKCE verifier); single use."""

    __tablename__ = "sso_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    state_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    provider: Mapped[str] = mapped_column(Unicode(50))
    nonce: Mapped[str] = mapped_column(Unicode(100))
    code_verifier: Mapped[str] = mapped_column(Unicode(128))
    return_to: Mapped[str] = mapped_column(Unicode(1000))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class Role(Base):
    """A named bundle of permissions. Built-in roles are synced from code (domain/access.py)."""

    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(Unicode(50), unique=True)
    name: Mapped[str] = mapped_column(ShortText)
    description: Mapped[str] = mapped_column(Text, default="")
    is_builtin: Mapped[bool] = mapped_column(default=False)

    permissions: Mapped[list[RolePermission]] = relationship(
        back_populates="role", cascade="all, delete-orphan"
    )


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission: Mapped[str] = mapped_column(Unicode(50), primary_key=True)

    role: Mapped[Role] = relationship(back_populates="permissions")


class RoleAssignment(Base):
    """Gives a user a role at a scope: global (both ids NULL), a department, or a section.

    `scope_key` repeats the scope as text ("section:7") so uniqueness works the same on every
    backend (NULLs in unique constraints behave differently on SQLite and MS SQL).
    """

    __tablename__ = "role_assignments"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", "scope_key"),
        CheckConstraint("department_id IS NULL OR section_id IS NULL", name="one_scope_only"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), index=True)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id"))
    scope_key: Mapped[str] = mapped_column(Unicode(40))

    user: Mapped[User] = relationship(back_populates="assignments")
    role: Mapped[Role] = relationship()
    department: Mapped[Department | None] = relationship()
    section: Mapped[Section | None] = relationship()

    @property
    def scope(self) -> Scope:
        if self.section_id is not None:
            return Scope(ScopeKind.SECTION, self.section_id)
        if self.department_id is not None:
            return Scope(ScopeKind.DEPARTMENT, self.department_id)
        return Scope(ScopeKind.GLOBAL)

    @scope.setter
    def scope(self, scope: Scope) -> None:
        self.department_id = scope.id if scope.kind is ScopeKind.DEPARTMENT else None
        self.section_id = scope.id if scope.kind is ScopeKind.SECTION else None
        self.scope_key = scope.key


class UserSession(Base):
    """A server-side login session. The cookie holds a random token; only its hash is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(Unicode(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    ip_address: Mapped[str | None] = mapped_column(Unicode(45))
    user_agent: Mapped[str | None] = mapped_column(Unicode(300))

    user: Mapped[User] = relationship()


class AuditEntry(Base):
    """Security-relevant actions (logins, account and permission changes)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(Unicode(60))
    target_type: Mapped[str | None] = mapped_column(Unicode(40))
    target_id: Mapped[str | None] = mapped_column(Unicode(60))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class LoginAttempt(Base):
    """Password login attempts, for throttling guessing (per account and per client address)."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)
    username: Mapped[str] = mapped_column(ShortText, index=True)
    ip_address: Mapped[str | None] = mapped_column(Unicode(45), index=True)
    success: Mapped[bool]
