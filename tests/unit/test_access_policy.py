"""The access policy matrix: who may view, edit, comment and manage, in which section.

Organization used throughout (like the sample data):
    STL (department 1): Quality (section 11), Process (12), Maintenance (13)
    R&D (department 2): Coatings (section 21)

Section-scoped permissions cover tasks (their section) and processes (their owning section: the
process's changes and map); the rest only counts when granted globally.
"""

import pytest

from taskboard.domain.access import (
    TOKEN_NEVER,
    VIEW_PERMISSIONS,
    BuiltinRole,
    Grant,
    GrantSet,
    Permission,
    Reach,
    Scope,
    SectionRef,
    TokenScope,
)

QUALITY = SectionRef(id=11, department_id=1)
PROCESS = SectionRef(id=12, department_id=1)
MAINTENANCE = SectionRef(id=13, department_id=1)
COATINGS = SectionRef(id=21, department_id=2)
ALL_SECTIONS = [QUALITY, PROCESS, MAINTENANCE, COATINGS]

V, E, C, D = (
    Permission.TASK_VIEW,
    Permission.TASK_EDIT,
    Permission.TASK_COMMENT,
    Permission.TASK_DELETE,
)
CV, CE, CC, CD = (
    Permission.CHANGE_VIEW,
    Permission.CHANGE_EDIT,
    Permission.CHANGE_COMMENT,
    Permission.CHANGE_DELETE,
)
KV, KE, KR = Permission.KNOWLEDGE_VIEW, Permission.KNOWLEDGE_EDIT, Permission.KNOWLEDGE_RELEASE
P, PE, U = Permission.PROJECT_MANAGE, Permission.PEOPLE_MANAGE, Permission.USERS_MANAGE
KC = Permission.KNOWLEDGE_CONFIGURE

# What the built-in roles give in a section they apply to (D-079).
VIEW = {V, CV, KV}
EDIT = VIEW | {E, C, CE, CC, KE, KR}
FULL = EDIT | {D, CD}
GLOBAL = {P, PE, U, KC}
SCOPED = sorted(FULL)


def role(builtin: BuiltinRole, scope: Scope) -> list[Grant]:
    return [Grant(p, scope) for p in builtin.permissions]


PRINCIPALS: dict[str, GrantSet] = {
    "admin": GrantSet(role(BuiltinRole.ADMIN, Scope.everywhere())),
    "quality editor": GrantSet(role(BuiltinRole.EDITOR, Scope.section(QUALITY.id))),
    "STL editor": GrantSet(role(BuiltinRole.EDITOR, Scope.department(1))),
    "viewer": GrantSet(role(BuiltinRole.VIEWER, Scope.everywhere())),
    "anonymous (default)": GrantSet(role(BuiltinRole.VIEWER, Scope.everywhere())),
    "anonymous (revoked)": GrantSet(),
    "quality editor + global viewer": GrantSet(
        role(BuiltinRole.EDITOR, Scope.section(QUALITY.id))
        + role(BuiltinRole.VIEWER, Scope.everywhere())
    ),
    # A global permission granted at a narrower scope must not leak into a global right.
    "admin role on one section": GrantSet(role(BuiltinRole.ADMIN, Scope.section(QUALITY.id))),
}

# Expected permissions per principal and section. "manage" = the global permissions.
EXPECTED: dict[str, dict[str, set[Permission]]] = {
    "admin": dict.fromkeys(("quality", "process", "coatings"), FULL) | {"manage": GLOBAL},
    "quality editor": {"quality": EDIT, "process": set(), "coatings": set(), "manage": set()},
    "STL editor": {"quality": EDIT, "process": EDIT, "coatings": set(), "manage": set()},
    "viewer": {"quality": VIEW, "process": VIEW, "coatings": VIEW, "manage": set()},
    "anonymous (default)": {"quality": VIEW, "process": VIEW, "coatings": VIEW, "manage": set()},
    "anonymous (revoked)": {"quality": set(), "process": set(), "coatings": set(), "manage": set()},
    "quality editor + global viewer": {
        "quality": EDIT,
        "process": VIEW,
        "coatings": VIEW,
        "manage": set(),
    },
    "admin role on one section": {
        "quality": FULL,
        "process": set(),
        "coatings": set(),
        "manage": set(),
    },
}
SECTIONS = {"quality": QUALITY, "process": PROCESS, "coatings": COATINGS}
CASES = [(who, where) for who, rows in EXPECTED.items() for where in rows]


@pytest.mark.parametrize(("who", "where"), CASES)
def test_policy_matrix(who: str, where: str) -> None:
    grants = PRINCIPALS[who]
    if where == "manage":
        allowed = {p for p in GLOBAL if grants.allows(p)}
    else:
        allowed = {p for p in SCOPED if grants.allows(p, SECTIONS[where])}
    assert allowed == EXPECTED[who][where]


def test_every_permission_is_covered_by_the_matrix() -> None:
    assert set(SCOPED) | GLOBAL == set(Permission)
    assert {p for p in Permission if p.is_scoped} == set(SCOPED)


def test_process_rights_follow_the_owning_section() -> None:
    """A process owned by STL › Process: a Quality editor may read its changes and map only
    through a wider grant, never edit them (D-080)."""
    quality_editor = PRINCIPALS["quality editor + global viewer"]
    assert quality_editor.allows(CV, PROCESS) and quality_editor.allows(KV, PROCESS)
    assert not quality_editor.allows(CE, PROCESS) and not quality_editor.allows(KE, PROCESS)
    assert PRINCIPALS["STL editor"].allows(KR, PROCESS)
    assert not PRINCIPALS["STL editor"].allows(CD, PROCESS)  # deleting: Administrators only


def test_reach_resolves_department_grants_into_sections() -> None:
    reach = PRINCIPALS["STL editor"].reach(E, ALL_SECTIONS)
    assert reach == Reach(everywhere=False, section_ids=frozenset({11, 12, 13}))
    assert reach.includes(12) and not reach.includes(21)


def test_reach_everywhere_and_nowhere() -> None:
    assert PRINCIPALS["viewer"].reach(V, ALL_SECTIONS).everywhere
    assert PRINCIPALS["anonymous (revoked)"].reach(V, ALL_SECTIONS).nowhere
    assert PRINCIPALS["STL editor"].reach(U, ALL_SECTIONS).nowhere


def test_allows_somewhere_drives_ui_affordances() -> None:
    assert PRINCIPALS["quality editor"].allows_somewhere(E)
    assert not PRINCIPALS["viewer"].allows_somewhere(E)
    assert not PRINCIPALS["admin role on one section"].allows_somewhere(U)


def test_scoped_permission_without_section_means_everywhere() -> None:
    assert PRINCIPALS["viewer"].allows(V)
    assert not PRINCIPALS["STL editor"].allows(E)


def test_scope_validation() -> None:
    with pytest.raises(ValueError, match="global scope has no id"):
        Scope(Scope.everywhere().kind, 3)


def test_tokens_keep_their_scope_and_never_administer() -> None:
    """D-097: a read token keeps the view rights; a write token everything but administration."""
    assert TokenScope.READ.permissions == frozenset(VIEW_PERMISSIONS)
    assert TokenScope.WRITE.permissions == frozenset(Permission) - TOKEN_NEVER
    assert {Permission.USERS_MANAGE, Permission.PEOPLE_MANAGE} == TOKEN_NEVER
    assert all(p.value.endswith(".view") for p in TokenScope.READ.permissions)
