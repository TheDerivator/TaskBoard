"""Map an external (SSO) identity to a local user, honouring what an admin set up in advance.

Order of matching:
1. A user already linked to (provider, subject) → that user.
2. Otherwise a user whose email equals the identity's email (pre-provisioned by an admin, often
   with status *pending* and role assignments) → link it and activate it.
3. Otherwise (providers without email, such as Windows sign-in) a user whose username equals the
   identity's username hint → link it the same way.
4. Otherwise, per configuration: reject (invite-only), or create an account without any rights.
Built-in accounts are never linked by email or username. Suspended users are refused whatever
the provider says. The identity's groups are remembered for group → role mappings.
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from taskboard.config import UnknownUserPolicy
from taskboard.db.base import normalize_email, utcnow
from taskboard.db.models import ExternalIdentity as IdentityLink
from taskboard.db.models import User
from taskboard.domain.access import UserKind, UserStatus
from taskboard.domain.errors import InvalidCredentialsError, PermissionDeniedError
from taskboard.identity.providers import ExternalIdentity

LAST_SEEN_RESOLUTION = timedelta(hours=1)


def _unique_username(session: Session, wanted: str) -> str:
    base = wanted.strip().lower()[:90] or "user"
    candidate, n = base, 1
    while session.scalar(select(User.id).where(User.username == candidate)) is not None:
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def resolve_user(
    session: Session, identity: ExternalIdentity, unknown_users: UnknownUserPolicy
) -> tuple[User, str]:
    """The local user for `identity`, plus what happened ("known", "linked" or "created")."""
    link = session.scalars(
        select(IdentityLink).where(
            IdentityLink.provider == identity.provider, IdentityLink.subject == identity.subject
        )
    ).one_or_none()
    outcome = "known"
    if link is not None:
        user = link.user
    else:
        user, outcome = _link_or_create(session, identity, unknown_users)
        link = IdentityLink(provider=identity.provider, subject=identity.subject)
        user.external_identities.append(link)

    if user.status is UserStatus.SUSPENDED:
        raise PermissionDeniedError("this account is suspended")
    if user.status is UserStatus.PENDING:
        user.status = UserStatus.ACTIVE
    groups = sorted(set(identity.groups))
    if (link.groups or []) != groups:
        link.groups = groups
    now = utcnow()
    # Ambient providers identify every request: only write "last seen" once in a while.
    if link.last_seen_at is None or now - link.last_seen_at > LAST_SEEN_RESOLUTION:
        link.last_seen_at = now
        user.last_login_at = now
    return user, outcome


def _invited(session: Session, identity: ExternalIdentity, condition: object) -> User | None:
    """A linkable prepared account: regular, not built-in, not yet linked to this provider."""
    candidate = session.scalars(
        select(User).where(
            condition,  # type: ignore[arg-type]
            User.kind == UserKind.REGULAR,
            User.is_builtin.is_(False),
        )
    ).one_or_none()
    if candidate is None or any(
        i.provider == identity.provider for i in candidate.external_identities
    ):
        return None
    return candidate


def _link_or_create(
    session: Session, identity: ExternalIdentity, unknown_users: UnknownUserPolicy
) -> tuple[User, str]:
    email = normalize_email(identity.email)
    if email and (invited := _invited(session, identity, User.email == email)):
        return invited, "linked"
    if identity.username and (
        invited := _invited(session, identity, User.username == identity.username.lower())
    ):
        return invited, "linked"
    if unknown_users is UnknownUserPolicy.CREATE:
        user = User(
            username=_unique_username(
                session, identity.username or email or f"{identity.provider}-{identity.subject}"
            ),
            display_name=identity.display_name or email or identity.subject,
            email=email,
        )
        session.add(user)
        return user, "created"
    raise InvalidCredentialsError("no account has been set up for you; ask an administrator")
