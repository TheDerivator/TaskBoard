"""The one place that decides what a principal can see: every task query goes through it, and
so does the question "may this visitor see the board at all" (tasks, process changes, knowledge).
"""

from sqlalchemy import Select, select

from taskboard.db.models import Change, Process, Task
from taskboard.domain.access import VIEW_PERMISSIONS, Permission
from taskboard.domain.errors import AuthenticationRequiredError, PasswordChangeRequiredError
from taskboard.identity.principal import Principal


def ensure_usable(principal: Principal) -> None:
    """Accounts that must change their password can do nothing else first."""
    if principal.must_change_password:
        raise PasswordChangeRequiredError("set a new password first")


def can_view_anything(principal: Principal) -> bool:
    """Tasks, process changes or process knowledge, somewhere."""
    return any(not principal.reach(p).nowhere for p in VIEW_PERMISSIONS)


def can_view_tasks(principal: Principal) -> bool:
    return not principal.reach(Permission.TASK_VIEW).nowhere


def require_board_access(principal: Principal) -> bool:
    """True if the principal may see some of the board (then also its people and processes).

    Raises for anonymous visitors who may see nothing, so the frontend asks them to log in.
    """
    ensure_usable(principal)
    if can_view_anything(principal):
        return True
    if principal.is_anonymous:
        raise AuthenticationRequiredError("log in to see the board")
    return False


def visible_tasks[*Ts](query: Select[*Ts], principal: Principal) -> Select[*Ts]:
    """Restrict a query on Task to the sections the principal may view.

    Anonymous visitors who may view nothing get 401 (the board is login-only); logged-in users
    without any view rights simply see nothing.
    """
    ensure_usable(principal)
    reach = principal.reach(Permission.TASK_VIEW)
    if reach.nowhere and principal.is_anonymous:
        raise AuthenticationRequiredError("log in to see the board")
    if reach.everywhere:
        return query
    return query.where(Task.section_id.in_(reach.section_ids))


def visible_changes[*Ts](query: Select[*Ts], principal: Principal) -> Select[*Ts]:
    """Restrict a query on Change to processes whose owning section grants `change.view` (D-080).

    Like tasks: anonymous visitors who may see none get 401, logged-in users simply see nothing.
    """
    ensure_usable(principal)
    reach = principal.reach(Permission.CHANGE_VIEW)
    if reach.nowhere and principal.is_anonymous:
        raise AuthenticationRequiredError("log in to see process changes")
    if reach.everywhere:
        return query
    in_reach = select(Process.id).where(Process.section_id.in_(reach.section_ids))
    return query.where(Change.process_id.in_(in_reach))
