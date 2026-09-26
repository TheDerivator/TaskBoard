"""The access policy matrix: who may view, edit, comment and manage, in which section.

Organization used throughout (like the sample data):
    STL (department 1): Quality (section 11), Process (12), Maintenance (13)
    R&D (department 2): Coatings (section 21)
"""

import pytest

from taskboard.domain.access import (
    BuiltinRole,
    Grant,
    GrantSet,
    Permission,
    Reach,
    Scope,
    SectionRef,
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
P, PE, U = Permission.PROJECT_MANAGE, Permission.PEOPLE_MANAGE, Permission.USERS_MANAGE


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

# Expected permissions per principal and section. "manage" = project/people/users management.
EXPECTED: dict[str, dict[str, set[Permission]]] = {
    "admin": {s: {V, E, C, D} for s in ("quality", "process", "coatings")} | {"manage": {P, PE, U}},
    "quality editor": {"quality": {V, E, C}, "process": set(), "coatings": set(), "manage": set()},
    "STL editor": {"quality": {V, E, C}, "process": {V, E, C}, "coatings": set(), "manage": set()},
    "viewer": {"quality": {V}, "process": {V}, "coatings": {V}, "manage": set()},
    "anonymous (default)": {"quality": {V}, "process": {V}, "coatings": {V}, "manage": set()},
    "anonymous (revoked)": {"quality": set(), "process": set(), "coatings": set(), "manage": set()},
    "quality editor + global viewer": {
        "quality": {V, E, C},
        "process": {V},
        "coatings": {V},
        "manage": set(),
    },
    "admin role on one section": {
        "quality": {V, E, C, D},
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
        allowed = {p for p in (P, PE, U) if grants.allows(p)}
    else:
        allowed = {p for p in (V, E, C, D) if grants.allows(p, SECTIONS[where])}
    assert allowed == EXPECTED[who][where]


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
