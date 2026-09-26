"""Append-only audit trail of security-relevant actions (account, role and login events)."""

from typing import Any

from sqlalchemy.orm import Session

from taskboard.db.models import AuditEntry


def record(
    session: Session,
    action: str,
    *,
    actor_user_id: int | None,
    target_type: str | None = None,
    target_id: object = None,
    **details: Any,
) -> None:
    """Add an audit entry to the current transaction (it is committed with the change itself)."""
    session.add(
        AuditEntry(
            action=action,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=None if target_id is None else str(target_id),
            details=details,
        )
    )
