"""User administration: accounts, passwords, role assignments, custom roles, the audit log.

Everything here needs `users.manage` and is recorded in the audit log. A guard refuses any change
that would leave no active account able to manage users (so admins cannot lock everyone out).
"""

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from taskboard.db.models import (
    AuditEntry,
    Department,
    GroupRoleMapping,
    Person,
    Role,
    RoleAssignment,
    RolePermission,
    Section,
    User,
)
from taskboard.domain.access import (
    PERMISSION_DESCRIPTIONS,
    Permission,
    Scope,
    ScopeKind,
    UserKind,
    UserStatus,
)
from taskboard.domain.errors import ConflictError, NotFoundError, RuleViolationError
from taskboard.identity import sessions
from taskboard.identity.passwords import generate_password, hash_password, password_problems
from taskboard.identity.principal import Principal
from taskboard.schemas.admin import (
    AssignmentIn,
    AssignmentOut,
    AuditEntryOut,
    ExternalIdentityOut,
    GroupMappingIn,
    GroupMappingOut,
    PasswordReset,
    PasswordResetOut,
    PermissionInfo,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from taskboard.services import audit
from taskboard.services.visibility import ensure_usable


class UserAdminService:
    def __init__(self, session: Session, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        ensure_usable(principal)
        principal.require(Permission.USERS_MANAGE)

    # ------------------------------------------------------------------ helpers

    def _record(self, action: str, target_type: str, target_id: object, **details: object) -> None:
        audit.record(
            self.session,
            action,
            actor_user_id=self.principal.user_id,
            target_type=target_type,
            target_id=target_id,
            **details,
        )

    def _user(self, user_id: int) -> User:
        user = self.session.get(User, user_id)
        if user is None:
            raise NotFoundError(f"no user {user_id}")
        return user

    def _scope_label(self, scope: Scope) -> str:
        if scope.kind is ScopeKind.GLOBAL:
            return "Everywhere"
        if scope.kind is ScopeKind.DEPARTMENT:
            department = self.session.get(Department, scope.id)
            return department.code if department else "?"
        section = self.session.get(Section, scope.id)
        if section is None:
            return "?"
        return f"{section.department.code} · {section.name}"

    def _user_out(self, user: User) -> UserOut:
        return UserOut(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            email=user.email,
            person_id=user.person_id,
            status=user.status,
            kind=user.kind,
            is_builtin=user.is_builtin,
            has_password=user.password_hash is not None,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            external_identities=[
                ExternalIdentityOut(
                    provider=i.provider, subject=i.subject, last_seen_at=i.last_seen_at
                )
                for i in user.external_identities
            ],
            assignments=[
                AssignmentOut(
                    id=a.id,
                    role_id=a.role_id,
                    role_name=a.role.name,
                    scope=a.scope.kind,
                    scope_id=a.scope.id,
                    scope_label=self._scope_label(a.scope),
                )
                for a in sorted(user.assignments, key=lambda a: a.id)
            ],
        )

    def _ensure_an_administrator_remains(self) -> None:
        self.session.flush()
        count = self.session.scalar(
            select(func.count(distinct(User.id)))
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .join(RolePermission, RolePermission.role_id == RoleAssignment.role_id)
            .where(
                User.status == UserStatus.ACTIVE,
                User.kind == UserKind.REGULAR,
                RoleAssignment.scope_key == Scope.everywhere().key,
                RolePermission.permission == Permission.USERS_MANAGE.value,
            )
        )
        if not count:
            raise RuleViolationError(
                "this would leave nobody able to manage users; "
                "keep at least one active administrator"
            )

    def _check_unique(
        self, user: User | None, *, username: str | None = None, email: str | None = None
    ) -> None:
        own_id = user.id if user else None
        if username is not None:
            clash = self.session.scalar(select(User.id).where(User.username == username.lower()))
            if clash is not None and clash != own_id:
                raise ConflictError(f"the username {username} is taken")
        if email is not None:
            clash = self.session.scalar(select(User.id).where(User.email == email.strip().lower()))
            if clash is not None and clash != own_id:
                raise ConflictError(f"another account already uses {email}")

    def _check_person(self, user: User | None, person_id: int | None) -> None:
        if person_id is None:
            return
        if self.session.get(Person, person_id) is None:
            raise RuleViolationError(f"unknown person {person_id}")
        linked = self.session.scalar(select(User.id).where(User.person_id == person_id))
        if linked is not None and (user is None or linked != user.id):
            raise ConflictError("that person is already linked to another account")

    def _scope(self, data: AssignmentIn) -> Scope:
        if data.scope is ScopeKind.GLOBAL:
            return Scope.everywhere()
        if data.scope_id is None:
            raise RuleViolationError("choose the department or section")
        model = Department if data.scope is ScopeKind.DEPARTMENT else Section
        if self.session.get(model, data.scope_id) is None:
            raise RuleViolationError(f"unknown {data.scope.value} {data.scope_id}")
        return Scope(data.scope, data.scope_id)

    def _assign(self, user: User, data: AssignmentIn) -> RoleAssignment:
        role = self.session.get(Role, data.role_id)
        if role is None:
            raise RuleViolationError(f"unknown role {data.role_id}")
        scope = self._scope(data)
        if any(a.role_id == role.id and a.scope_key == scope.key for a in user.assignments):
            raise ConflictError(f"{user.username} already has {role.name} there")
        assignment = RoleAssignment(role=role)
        assignment.scope = scope
        user.assignments.append(assignment)
        return assignment

    # ------------------------------------------------------------------ users

    def list_users(self) -> list[UserOut]:
        users = self.session.scalars(
            select(User)
            .options(selectinload(User.assignments), selectinload(User.external_identities))
            .order_by(User.kind.desc(), User.display_name)
        )
        return [self._user_out(u) for u in users]

    def create_user(self, data: UserCreate) -> UserCreated:
        self._check_unique(None, username=data.username, email=data.email)
        self._check_person(None, data.person_id)
        generated: str | None = None
        user = User(
            username=data.username,
            display_name=data.display_name,
            email=data.email,
            person_id=data.person_id,
        )
        if data.sso_only:
            user.status = UserStatus.PENDING
        else:
            password = data.password or generate_password()
            if data.password is None:
                generated = password
            elif problems := password_problems(password):
                raise RuleViolationError("password " + "; ".join(problems))
            user.password_hash = hash_password(password)
            user.must_change_password = True  # the person chooses their own at first login
        self.session.add(user)
        for assignment in data.assignments:
            self._assign(user, assignment)
        self.session.flush()
        self._record(
            "user.created",
            "user",
            user.id,
            username=user.username,
            sso_only=data.sso_only,
            roles=[f"{a.role.key}@{a.scope_key}" for a in user.assignments],
        )
        self.session.commit()
        return UserCreated(user=self._user_out(user), generated_password=generated)

    def update_user(self, user_id: int, data: UserUpdate) -> UserOut:
        user = self._user(user_id)
        sent = data.model_fields_set
        changes: dict[str, object] = {}
        if data.display_name is not None and data.display_name != user.display_name:
            user.display_name = changes["display_name"] = data.display_name
        if "email" in sent:
            self._check_unique(user, email=data.email)
            user.email = data.email
            changes["email"] = user.email
        if "person_id" in sent:
            self._check_person(user, data.person_id)
            user.person_id = changes["person_id"] = data.person_id
        if data.status is not None and data.status is not user.status:
            if user.kind is UserKind.ANONYMOUS:
                raise RuleViolationError(
                    "the anonymous visitor cannot be suspended; remove its roles instead"
                )
            if user.id == self.principal.user_id:
                raise RuleViolationError("you cannot change the status of your own account")
            user.status = data.status
            changes["status"] = data.status.value
            if data.status is not UserStatus.ACTIVE:
                sessions.end_all_sessions(self.session, user.id)
        self._ensure_an_administrator_remains()
        if changes:
            self._record("user.updated", "user", user.id, **changes)
        self.session.commit()
        return self._user_out(user)

    def reset_password(self, user_id: int, data: PasswordReset) -> PasswordResetOut:
        user = self._user(user_id)
        if user.kind is UserKind.ANONYMOUS:
            raise RuleViolationError("the anonymous visitor has no password")
        password = data.password or generate_password()
        if data.password is not None and (problems := password_problems(password)):
            raise RuleViolationError("password " + "; ".join(problems))
        user.password_hash = hash_password(password)
        user.must_change_password = True
        sessions.end_all_sessions(self.session, user.id)
        self._record("user.password_reset", "user", user.id)
        self.session.commit()
        return PasswordResetOut(generated_password=None if data.password else password)

    def add_assignment(self, user_id: int, data: AssignmentIn) -> UserOut:
        user = self._user(user_id)
        assignment = self._assign(user, data)
        self.session.flush()
        self._record(
            "user.role_granted",
            "user",
            user.id,
            role=assignment.role.key,
            scope=assignment.scope_key,
        )
        self.session.commit()
        return self._user_out(user)

    def remove_assignment(self, user_id: int, assignment_id: int) -> UserOut:
        user = self._user(user_id)
        assignment = next((a for a in user.assignments if a.id == assignment_id), None)
        if assignment is None:
            raise NotFoundError(f"no assignment {assignment_id} for this user")
        role_key, scope_key = assignment.role.key, assignment.scope_key
        user.assignments.remove(assignment)
        self._ensure_an_administrator_remains()
        self._record("user.role_revoked", "user", user.id, role=role_key, scope=scope_key)
        self.session.commit()
        return self._user_out(user)

    # ------------------------------------------------------------------ roles

    @staticmethod
    def permissions() -> list[PermissionInfo]:
        return [
            PermissionInfo(value=p, scoped=p.is_scoped, description=PERMISSION_DESCRIPTIONS[p])
            for p in Permission
        ]

    def _role_out(self, role: Role) -> RoleOut:
        known = {p.value for p in Permission}
        count = self.session.scalar(select(func.count()).where(RoleAssignment.role_id == role.id))
        return RoleOut(
            id=role.id,
            key=role.key,
            name=role.name,
            description=role.description,
            is_builtin=role.is_builtin,
            permissions=[
                Permission(rp.permission) for rp in role.permissions if rp.permission in known
            ],
            assignment_count=count or 0,
        )

    def list_roles(self) -> list[RoleOut]:
        roles = self.session.scalars(select(Role).order_by(Role.is_builtin.desc(), Role.id))
        return [self._role_out(r) for r in roles]

    def _custom_role(self, role_id: int) -> Role:
        role = self.session.get(Role, role_id)
        if role is None:
            raise NotFoundError(f"no role {role_id}")
        if role.is_builtin:
            raise RuleViolationError(
                "built-in roles are defined by the application and cannot change"
            )
        return role

    def create_role(self, data: RoleCreate) -> RoleOut:
        if self.session.scalar(select(Role.id).where(Role.key == data.key)) is not None:
            raise ConflictError(f"a role with key {data.key} exists")
        role = Role(key=data.key, name=data.name, description=data.description)
        role.permissions = [
            RolePermission(permission=p.value) for p in sorted(set(data.permissions))
        ]
        self.session.add(role)
        self.session.flush()
        self._record(
            "role.created",
            "role",
            role.id,
            key=role.key,
            permissions=sorted(p.value for p in data.permissions),
        )
        self.session.commit()
        return self._role_out(role)

    def update_role(self, role_id: int, data: RoleUpdate) -> RoleOut:
        role = self._custom_role(role_id)
        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        if data.permissions is not None:
            role.permissions = [
                RolePermission(permission=p.value) for p in sorted(set(data.permissions))
            ]
        self._ensure_an_administrator_remains()
        self._record(
            "role.updated", "role", role.id, **data.model_dump(exclude_none=True, mode="json")
        )
        self.session.commit()
        return self._role_out(role)

    def delete_role(self, role_id: int) -> None:
        role = self._custom_role(role_id)
        if self.session.scalar(select(func.count()).where(RoleAssignment.role_id == role.id)):
            raise ConflictError("the role is still assigned; remove those assignments first")
        self._record("role.deleted", "role", role.id, key=role.key)
        self.session.delete(role)
        self.session.commit()

    # ------------------------------------------------------------------ SSO group mappings

    def _mapping_out(self, mapping: GroupRoleMapping) -> GroupMappingOut:
        return GroupMappingOut(
            id=mapping.id,
            provider=mapping.provider,
            group_name=mapping.group_name,
            role_id=mapping.role_id,
            role_name=mapping.role.name,
            scope=mapping.scope.kind,
            scope_id=mapping.scope.id,
            scope_label=self._scope_label(mapping.scope),
        )

    def list_group_mappings(self) -> list[GroupMappingOut]:
        mappings = self.session.scalars(
            select(GroupRoleMapping).order_by(
                GroupRoleMapping.provider, GroupRoleMapping.group_name
            )
        )
        return [self._mapping_out(m) for m in mappings]

    def add_group_mapping(self, data: GroupMappingIn) -> GroupMappingOut:
        role = self.session.get(Role, data.role_id)
        if role is None:
            raise RuleViolationError(f"unknown role {data.role_id}")
        scope = self._scope(
            AssignmentIn(role_id=data.role_id, scope=data.scope, scope_id=data.scope_id)
        )
        clash = self.session.scalar(
            select(GroupRoleMapping.id).where(
                GroupRoleMapping.provider == data.provider,
                GroupRoleMapping.group_name == data.group_name,
                GroupRoleMapping.role_id == role.id,
                GroupRoleMapping.scope_key == scope.key,
            )
        )
        if clash is not None:
            raise ConflictError("this group already has that role there")
        mapping = GroupRoleMapping(provider=data.provider, group_name=data.group_name, role=role)
        mapping.scope = scope
        self.session.add(mapping)
        self.session.flush()
        self._record(
            "group_mapping.created",
            "group_mapping",
            mapping.id,
            provider=mapping.provider,
            group=mapping.group_name,
            role=role.key,
            scope=scope.key,
        )
        self.session.commit()
        return self._mapping_out(mapping)

    def delete_group_mapping(self, mapping_id: int) -> None:
        mapping = self.session.get(GroupRoleMapping, mapping_id)
        if mapping is None:
            raise NotFoundError(f"no group mapping {mapping_id}")
        self._record(
            "group_mapping.deleted",
            "group_mapping",
            mapping.id,
            provider=mapping.provider,
            group=mapping.group_name,
            role=mapping.role.key,
            scope=mapping.scope_key,
        )
        self.session.delete(mapping)
        self.session.commit()

    # ------------------------------------------------------------------ audit log

    def audit_log(self, *, limit: int = 100, before_id: int | None = None) -> list[AuditEntryOut]:
        query = (
            select(AuditEntry, User.display_name)
            .outerjoin(User, User.id == AuditEntry.actor_user_id)
            .order_by(AuditEntry.id.desc())
            .limit(min(max(limit, 1), 500))
        )
        if before_id is not None:
            query = query.where(AuditEntry.id < before_id)
        return [
            AuditEntryOut(
                id=entry.id,
                at=entry.at,
                actor=actor,
                action=entry.action,
                target_type=entry.target_type,
                target_id=entry.target_id,
                details=entry.details,
            )
            for entry, actor in self.session.execute(query)
        ]
