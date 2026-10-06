"""API tokens for AI agents and scripts (D-097): `Authorization: Bearer tb_…`, only the hash stored.

A token acts as its owner with the owner's current rights, narrowed by its scope (read or write;
never administration). Like sessions, it is checked on every request, so revoking it, its expiry
or suspending the owner takes effect at once.
"""

import hashlib
import secrets
from dataclasses import replace
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from taskboard.db.base import utcnow
from taskboard.db.models import ApiToken, User
from taskboard.domain.access import GrantSet, TokenScope, UserStatus
from taskboard.identity.principal import Principal, principal_for_user

PREFIX = "tb_"
# "Last used" is written at most this often per token, so reading costs no write per request.
TOUCH_INTERVAL = timedelta(minutes=1)


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue(
    session: Session,
    user_id: int,
    *,
    name: str,
    scope: TokenScope,
    expires_at: datetime | None,
) -> tuple[ApiToken, str]:
    """Create a token; returns the row and the secret, which is shown once and never stored."""
    secret = PREFIX + secrets.token_urlsafe(32)
    token = ApiToken(
        user_id=user_id,
        name=name,
        token_hash=_hash(secret),
        prefix=secret[: len(PREFIX) + 6],
        scope=scope,
        expires_at=expires_at,
    )
    session.add(token)
    session.flush()
    return token, secret


def is_live(token: ApiToken, now: datetime | None = None) -> bool:
    """Not revoked and not expired."""
    now = now or utcnow()
    return token.revoked_at is None and (token.expires_at is None or token.expires_at > now)


def principal_for_secret(session: Session, secret: str) -> Principal | None:
    """The owner as seen through a live token (narrowed to its scope); None when the token is
    unknown, revoked or expired, or its owner is not active."""
    row = session.execute(
        select(ApiToken, User)
        .join(User, User.id == ApiToken.user_id)
        .where(ApiToken.token_hash == _hash(secret))
    ).first()
    if row is None:
        return None
    token, user = row
    if not is_live(token) or user.status is not UserStatus.ACTIVE:
        return None
    principal = principal_for_user(session, user)
    allowed = token.scope.permissions
    return replace(
        principal,
        grants=GrantSet(g for g in principal.grants if g.permission in allowed),
        token_id=token.id,
        token_name=token.name,
        token_scope=token.scope,
        token_last_used_at=token.last_used_at,
    )


def due_for_touch(principal: Principal) -> bool:
    last = principal.token_last_used_at
    return principal.token_id is not None and (last is None or utcnow() - last >= TOUCH_INTERVAL)


def touch(session: Session, token_id: int, *, ip_address: str | None) -> None:
    """Record that the token was just used (the caller commits)."""
    session.execute(
        update(ApiToken)
        .where(ApiToken.id == token_id)
        .values(last_used_at=utcnow(), last_used_ip=ip_address)
    )
