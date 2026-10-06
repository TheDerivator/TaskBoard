"""Who did something, as shown in timelines and histories: the user, and the API token they did it
through ("Anna Claes via Claude Code", D-097)."""

from sqlalchemy.orm import Session

from taskboard.db.models import ApiToken, User
from taskboard.schemas.conversation import Actor


def actor(session: Session, user: User, token_id: int | None = None) -> Actor:
    token = session.get(ApiToken, token_id) if token_id is not None else None
    return Actor(
        user_id=user.id,
        display_name=user.display_name,
        person_id=user.person_id,
        via=token.name if token else None,
    )


def actor_by_id(session: Session, user_id: int | None, token_id: int | None = None) -> Actor | None:
    user = session.get(User, user_id) if user_id is not None else None
    return actor(session, user, token_id) if user is not None else None
