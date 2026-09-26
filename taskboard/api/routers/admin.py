"""Administration endpoints: users, passwords, role assignments, roles, organization, audit log."""

from fastapi import APIRouter, status

from taskboard.api.deps import Organization, Providers, UserAdmin
from taskboard.schemas.admin import (
    AssignmentIn,
    AuditEntryOut,
    DepartmentIn,
    DepartmentUpdate,
    GroupMappingIn,
    GroupMappingOut,
    PasswordReset,
    PasswordResetOut,
    PermissionInfo,
    PersonAdminOut,
    PersonIn,
    PersonUpdate,
    ProviderInfo,
    RoleCreate,
    RoleOut,
    RoleUpdate,
    SectionIn,
    SectionUpdate,
    UserCreate,
    UserCreated,
    UserOut,
    UserUpdate,
)
from taskboard.schemas.reference import DepartmentOut

router = APIRouter(prefix="/admin", tags=["administration"])

# ---------------------------------------------------------------- users (users.manage)


@router.get("/users")
def list_users(admin: UserAdmin) -> list[UserOut]:
    return admin.list_users()


@router.post("/users", status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, admin: UserAdmin) -> UserCreated:
    """A local account (password given or generated, changed at first login) or, with
    `sso_only`, a pre-provisioned account that the first SSO login with this email activates."""
    return admin.create_user(body)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, admin: UserAdmin) -> UserOut:
    """Suspending logs the account out everywhere at once."""
    return admin.update_user(user_id, body)


@router.post("/users/{user_id}/password")
def reset_password(user_id: int, body: PasswordReset, admin: UserAdmin) -> PasswordResetOut:
    return admin.reset_password(user_id, body)


@router.post("/users/{user_id}/assignments", status_code=status.HTTP_201_CREATED)
def add_assignment(user_id: int, body: AssignmentIn, admin: UserAdmin) -> UserOut:
    return admin.add_assignment(user_id, body)


@router.delete("/users/{user_id}/assignments/{assignment_id}")
def remove_assignment(user_id: int, assignment_id: int, admin: UserAdmin) -> UserOut:
    return admin.remove_assignment(user_id, assignment_id)


@router.get("/permissions")
def permissions(admin: UserAdmin) -> list[PermissionInfo]:
    """The permission catalog with descriptions (for editing roles)."""
    return admin.permissions()


@router.get("/roles")
def list_roles(admin: UserAdmin) -> list[RoleOut]:
    return admin.list_roles()


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(body: RoleCreate, admin: UserAdmin) -> RoleOut:
    return admin.create_role(body)


@router.patch("/roles/{role_id}")
def update_role(role_id: int, body: RoleUpdate, admin: UserAdmin) -> RoleOut:
    return admin.update_role(role_id, body)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: int, admin: UserAdmin) -> None:
    admin.delete_role(role_id)


@router.get("/sso-providers")
def sso_providers(admin: UserAdmin, providers: Providers) -> list[ProviderInfo]:
    """The configured SSO providers (empty when only built-in accounts are used)."""
    del admin  # only for the permission check
    return [
        *(
            ProviderInfo(name=p.name, display_name=p.display_name, kind="redirect")
            for p in providers.redirect.values()
        ),
        *(
            ProviderInfo(name=p.name, display_name=p.display_name, kind="ambient")
            for p in providers.ambient
        ),
    ]


@router.get("/group-mappings")
def list_group_mappings(admin: UserAdmin) -> list[GroupMappingOut]:
    """Identity-provider groups whose members hold a role (while they are in the group)."""
    return admin.list_group_mappings()


@router.post("/group-mappings", status_code=status.HTTP_201_CREATED)
def add_group_mapping(body: GroupMappingIn, admin: UserAdmin) -> GroupMappingOut:
    return admin.add_group_mapping(body)


@router.delete("/group-mappings/{mapping_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group_mapping(mapping_id: int, admin: UserAdmin) -> None:
    admin.delete_group_mapping(mapping_id)


@router.get("/audit")
def audit_log(
    admin: UserAdmin, limit: int = 100, before_id: int | None = None
) -> list[AuditEntryOut]:
    """Newest first; page back with `before_id`."""
    return admin.audit_log(limit=limit, before_id=before_id)


# ---------------------------------------------------------------- organization (people.manage)


@router.post("/departments", status_code=status.HTTP_201_CREATED)
def create_department(body: DepartmentIn, organization: Organization) -> DepartmentOut:
    return organization.create_department(body)


@router.patch("/departments/{department_id}")
def update_department(
    department_id: int, body: DepartmentUpdate, organization: Organization
) -> DepartmentOut:
    return organization.update_department(department_id, body)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_department(department_id: int, organization: Organization) -> None:
    organization.delete_department(department_id)


@router.post("/sections", status_code=status.HTTP_201_CREATED)
def create_section(body: SectionIn, organization: Organization) -> DepartmentOut:
    return organization.create_section(body)


@router.patch("/sections/{section_id}")
def update_section(
    section_id: int, body: SectionUpdate, organization: Organization
) -> DepartmentOut:
    return organization.update_section(section_id, body)


@router.delete("/sections/{section_id}")
def delete_section(section_id: int, organization: Organization) -> DepartmentOut:
    return organization.delete_section(section_id)


@router.get("/people")
def list_people(organization: Organization) -> list[PersonAdminOut]:
    """Everyone, including inactive people, with emails and linked accounts."""
    return organization.list_people()


@router.post("/people", status_code=status.HTTP_201_CREATED)
def create_person(body: PersonIn, organization: Organization) -> PersonAdminOut:
    return organization.create_person(body)


@router.patch("/people/{person_id}")
def update_person(person_id: int, body: PersonUpdate, organization: Organization) -> PersonAdminOut:
    return organization.update_person(person_id, body)
